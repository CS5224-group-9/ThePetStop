import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from urllib.parse import quote, urljoin, urlparse

from facilities.ingestion.aws import client as aws_client
from facilities.ingestion.dispatch import (
    batch_size_from_environment,
    create_batch_artifacts,
    dispatch_batches,
    resume_dispatch,
)
from facilities.ingestion.parsers import parse_registry_pdf

DEFAULT_SOURCES = {
    "vet": "https://avs.nparks.gov.sg/outreach/resources/public-registry-of-avs-licensed-veterinary-centres/",
    "pet_shop": "https://avs.nparks.gov.sg/outreach/resources/public-registry-of-avs-licensed-pet-shops/",
}
ALLOWED_HOSTS = {"avs.nparks.gov.sg", "isomer-user-content.by.gov.sg"}
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
TIMEOUT_SECONDS = 15


class RegistryFetchError(ValueError):
    pass


def _allowed_hosts():
    if os.environ.get("FACILITY_FIXTURE_MODE", "").lower() == "true":
        config = json.loads(os.environ["FACILITY_SOURCE_CONFIG"])
        return {urlparse(item["registry_url"]).hostname for item in config.values()}
    return ALLOWED_HOSTS


def _validate_url(url, allowed_hosts):
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise RegistryFetchError("Registry URL has an invalid port") from error
    allowed_schemes = {"https"}
    fixture_mode = os.environ.get("FACILITY_FIXTURE_MODE", "").lower() == "true"
    if fixture_mode:
        allowed_schemes.add("http")
    if parsed.scheme not in allowed_schemes or parsed.hostname not in allowed_hosts:
        raise RegistryFetchError("Registry URL is outside the configured source hosts")
    if not fixture_mode and port not in {None, 443}:
        raise RegistryFetchError("Registry URL uses a nonstandard port")
    return parsed._replace(
        path=quote(parsed.path, safe="/%:@!$&'()*+,;=-._~"),
        query=quote(parsed.query, safe="=&?/:@!$'()*+,;%-._~"),
    ).geturl()


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = {"href": dict(attrs).get("href", ""), "text": []}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.current["text"] = " ".join(self.current["text"])
            self.links.append(self.current)
            self.current = None


def _open(url, allowed_hosts):
    current_url = _validate_url(url, allowed_hosts)
    for attempt in range(2):
        try:
            for _ in range(4):
                parsed = urlparse(current_url)
                connection_type = (
                    HTTPSConnection if parsed.scheme == "https" else HTTPConnection
                )
                connection = connection_type(
                    parsed.hostname, parsed.port, timeout=TIMEOUT_SECONDS
                )
                path = parsed.path or "/"
                if parsed.query:
                    path += f"?{parsed.query}"
                try:
                    connection.request(
                        "GET",
                        path,
                        headers={"User-Agent": "ThePetStop facility registry sync"},
                    )
                    response = connection.getresponse()
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.getheader("Location")
                        if not location:
                            raise RegistryFetchError(
                                "Registry redirect has no location"
                            )
                        current_url = _validate_url(
                            urljoin(current_url, location), allowed_hosts
                        )
                        continue
                    if response.status != 200:
                        if response.status >= 500 and attempt == 0:
                            break
                        raise RegistryFetchError(
                            f"Registry returned HTTP {response.status}"
                        )
                    content = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise RegistryFetchError(
                            "Registry response exceeds the size limit"
                        )
                    return current_url, content
                finally:
                    connection.close()
            else:
                raise RegistryFetchError("Registry redirected too many times")
        except (OSError, HTTPException, TimeoutError) as error:
            if attempt:
                host = urlparse(current_url).hostname
                raise RegistryFetchError(
                    f"Registry request to {host} failed after retry "
                    f"({type(error).__name__})"
                ) from error
    raise RegistryFetchError("Registry request failed after retry")


def _source_config():
    config = json.loads(os.environ.get("FACILITY_SOURCE_CONFIG", "{}"))
    sources = {
        **{key: {"registry_url": value} for key, value in DEFAULT_SOURCES.items()},
        **config,
    }
    return sources


def _find_pdf(html, page_url, source, allowed_hosts):
    links = _Links()
    links.feed(html)
    terms = (
        ("vet", "veterinary")
        if source == "vet"
        else ("pet shop", "pet-shop", "petshop")
    )
    matches = []
    for link in links.links:
        href = link["href"].strip()
        label = f"{link['text']} {href}".lower()
        if ".pdf" in urlparse(href).path.lower() and any(
            term in label for term in terms
        ):
            matches.append(_validate_url(urljoin(page_url, href), allowed_hosts))
    matches = list(dict.fromkeys(matches))
    if len(matches) != 1:
        raise RegistryFetchError(
            f"Expected one {source} registry PDF link; found {len(matches)}"
        )
    return matches[0]


def fetch_registry(source, run_id=None, s3_client=None, sqs_client=None):
    if source not in DEFAULT_SOURCES:
        raise RegistryFetchError(f"Unsupported facility source: {source}")
    bucket = os.environ.get("FACILITY_SYNC_BUCKET")
    queue_url = os.environ.get("GEOCODE_QUEUE_URL")
    if not bucket or not queue_url or not queue_url.endswith(".fifo"):
        raise RegistryFetchError(
            "Configure FACILITY_SYNC_BUCKET and a FIFO GEOCODE_QUEUE_URL"
        )
    try:
        batch_size = batch_size_from_environment()
    except ValueError as error:
        raise RegistryFetchError(str(error)) from error
    config = _source_config()
    if source not in config or not config[source].get("registry_url"):
        raise RegistryFetchError(f"No registry URL configured for {source}")
    allowed_hosts = _allowed_hosts()
    registry_url = config[source]["registry_url"]
    page_url, page = _open(registry_url, allowed_hosts)
    document_url = _find_pdf(
        page.decode("utf-8", errors="replace"), page_url, source, allowed_hosts
    )
    _, pdf = _open(document_url, allowed_hosts)
    if not pdf.startswith(b"%PDF-"):
        raise RegistryFetchError("AVS registry download is not a PDF")

    run_id = str(uuid.UUID(run_id)) if run_id else str(uuid.uuid4())
    sha256 = hashlib.sha256(pdf).hexdigest()
    if s3_client is None:
        s3_client = aws_client("s3")
    prefix = f"runs/{source}/{run_id}"
    manifest_key = f"pending/{source}/{run_id}/manifest.json"
    try:
        existing_manifest = json.loads(
            s3_client.get_object(Bucket=bucket, Key=manifest_key)["Body"].read()
        )
    except s3_client.exceptions.NoSuchKey:
        existing_manifest = None
    if existing_manifest is not None:
        if existing_manifest.get("document_sha256") != sha256:
            raise RegistryFetchError(
                "A run ID cannot be reused for a different registry PDF"
            )
        if sqs_client is None:
            sqs_client = aws_client("sqs")
        return resume_dispatch(s3_client, sqs_client, queue_url, bucket, source, run_id)

    raw_key = f"raw/{source}/{sha256}.pdf"
    s3_client.put_object(
        Bucket=bucket,
        Key=raw_key,
        Body=pdf,
        ContentType="application/pdf",
        Metadata={"sha256": sha256},
    )

    records = parse_registry_pdf(pdf, source)
    retrieved_at = datetime.now(UTC).isoformat()
    batches, batch_keys, batch_versions = create_batch_artifacts(
        s3_client, bucket, source, run_id, records, batch_size
    )
    result = {
        "schema_version": 1,
        "run_id": run_id,
        "source": source,
        "registry_url": page_url,
        "document_url": document_url,
        "document_sha256": sha256,
        "raw_key": raw_key,
        "retrieved_at": retrieved_at,
        "parsed_count": len(records),
        "parser_version": "1",
        "expected_batch_ids": [batch["batch_id"] for batch in batches],
        "records": records,
    }
    parsed_key = f"{prefix}/parsed.json"
    s3_client.put_object(
        Bucket=bucket,
        Key=parsed_key,
        Body=json.dumps(result, separators=(",", ":")).encode("utf-8"),
        ContentType="application/json",
    )
    if sqs_client is None:
        sqs_client = aws_client("sqs")
    manifest_key = dispatch_batches(
        s3_client,
        sqs_client,
        queue_url,
        bucket,
        source,
        run_id,
        parsed_key,
        sha256,
        batches,
        batch_keys,
        batch_versions,
    )
    return {
        "run_id": run_id,
        "source": source,
        "document_sha256": sha256,
        "parsed_count": len(records),
        "batch_count": len(batches),
        "manifest_key": manifest_key,
    }


def handler(event, context):
    operation = event.get("operation")
    source = event.get("source", "")
    if operation not in {"start", "dispatch"}:
        raise RegistryFetchError("Supported operations are start and dispatch")
    if source not in DEFAULT_SOURCES:
        raise RegistryFetchError(f"Unsupported facility source: {source}")

    bucket = os.environ.get("FACILITY_SYNC_BUCKET")
    queue_url = os.environ.get("GEOCODE_QUEUE_URL")
    if not bucket or not queue_url or not queue_url.endswith(".fifo"):
        raise RegistryFetchError(
            "Configure FACILITY_SYNC_BUCKET and a FIFO GEOCODE_QUEUE_URL"
        )
    s3 = aws_client("s3")
    sqs = aws_client("sqs")
    if operation == "dispatch":
        try:
            run_id = str(uuid.UUID(event.get("run_id", "")))
        except ValueError as error:
            raise RegistryFetchError("dispatch requires a valid run_id") from error
        return resume_dispatch(s3, sqs, queue_url, bucket, source, run_id)
    return fetch_registry(source, event.get("run_id"), s3, sqs)
