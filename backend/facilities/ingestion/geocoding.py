import hashlib
import json
import math
import os
import re
import secrets
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from urllib.parse import urlencode, urlparse
from uuid import UUID

from facilities.ingestion import status as run_status
from facilities.ingestion.aws import client as aws_client
from facilities.ingestion.finalize import finalize_if_complete

RATE_STATE_KEY = "coordination/geocoding-worker.json"
MAX_RESPONSE_BYTES = 1_000_000
SINGAPORE_BOUNDS = (1.15, 1.5, 103.55, 104.15)
_token = None


class GeocodeError(RuntimeError):
    pass


class RetryableGeocodeError(GeocodeError):
    pass


class GeocoderConfigurationError(GeocodeError):
    pass


class _UpstreamError(GeocodeError):
    def __init__(self, status, retry_after=None):
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"OneMap returned HTTP {status}")


class _TokenRejected(GeocodeError):
    pass


def _read_json(s3, bucket, key, version=None):
    params = {"Bucket": bucket, "Key": key}
    if version:
        params["VersionId"] = version
    return json.loads(s3.get_object(**params)["Body"].read())


def _put_json(s3, bucket, key, value):
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(value, separators=(",", ":")).encode("utf-8"),
        ContentType="application/json",
    )


def _credentials():
    if arn := os.environ.get("ONEMAP_SECRET_ARN"):
        value = json.loads(
            aws_client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"]
        )
        return (
            value.get("access_token", ""),
            value.get("email", ""),
            value.get("password", ""),
        )
    return (
        os.environ.get("ONEMAP_ACCESS_TOKEN", ""),
        os.environ.get("ONEMAP_EMAIL", ""),
        os.environ.get("ONEMAP_PASSWORD", ""),
    )


def _token_value(force_refresh=False, before_request=lambda: None):
    global _token
    if _token and not force_refresh:
        return _token
    supplied, email, password = _credentials()
    supplied = supplied.strip()
    if supplied and not force_refresh:
        _token = supplied
        return _token
    if not email or not password:
        raise GeocoderConfigurationError(
            "Configure OneMap token or account credentials"
        )
    try:
        before_request()
        payload = _request(
            "/api/auth/post/getToken",
            method="POST",
            body={"email": email, "password": password},
        )
    except _TokenRejected as error:
        raise GeocoderConfigurationError(
            "OneMap rejected the configured credentials"
        ) from error
    except _UpstreamError as error:
        if error.status == 429 or error.status >= 500:
            raise
        raise GeocoderConfigurationError("OneMap token request was rejected") from error
    access_token = payload.get("access_token")
    expiry = payload.get("expiry_timestamp")
    try:
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError
        if float(expiry) <= time.time():
            raise ValueError
    except (TypeError, ValueError):
        raise GeocoderConfigurationError(
            "OneMap returned an invalid access token"
        ) from None
    _token = access_token.strip()
    return _token


def _request(path, *, method="GET", token=None, body=None):
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = token
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if os.environ.get("FACILITY_FIXTURE_MODE", "").lower() == "true":
        base = urlparse(os.environ["ONEMAP_FIXTURE_URL"])
        if (
            base.scheme != "http"
            or base.hostname not in {"fixtures", "localhost", "127.0.0.1"}
            or base.username
            or base.password
        ):
            raise GeocoderConfigurationError("Invalid local OneMap fixture URL")
        connection = HTTPConnection(base.hostname, base.port, timeout=8)
    else:
        connection = HTTPSConnection("www.onemap.gov.sg", timeout=8)
    try:
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        if response.status in {301, 302, 303, 307, 308}:
            raise GeocodeError("OneMap unexpectedly redirected the request")
        if response.status in {401, 403}:
            raise _TokenRejected from None
        if response.status != 200:
            raise _UpstreamError(
                response.status, response.getheader("Retry-After")
            ) from None
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise GeocodeError("OneMap response exceeds the size limit")
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise GeocodeError("OneMap response is not a JSON object")
        return result
    except (TimeoutError, OSError, HTTPException) as error:
        raise RetryableGeocodeError("OneMap request failed temporarily") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RetryableGeocodeError("OneMap returned invalid JSON") from error
    finally:
        connection.close()


def _search(query, before_request):
    path = "/api/common/elastic/search?" + urlencode(
        {
            "searchVal": query,
            "returnGeom": "Y",
            "getAddrDetails": "Y",
            "pageNum": 1,
        }
    )
    token = _token_value(before_request=before_request)
    for attempt in range(2):
        try:
            before_request()
            result = _request(path, token=token)
            if "error" in result:
                raise _TokenRejected
            rows = result.get("results")
            if not isinstance(rows, list):
                raise RetryableGeocodeError("OneMap search response has no result list")
            return rows
        except _TokenRejected:
            if attempt:
                raise GeocoderConfigurationError(
                    "OneMap rejected the refreshed token"
                ) from None
            token = _token_value(force_refresh=True, before_request=before_request)
    raise GeocoderConfigurationError("OneMap authentication failed")


def _retry_after_seconds(value, receive_count):
    if value:
        try:
            return max(1, int(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(1, int(retry_at.timestamp() - time.time()))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(300, 2 ** min(receive_count, 8)) + secrets.randbelow(3)


def _load_rate_state(s3, bucket):
    try:
        return _read_json(s3, bucket, RATE_STATE_KEY)
    except s3.exceptions.NoSuchKey:
        return {"next_request_at": 0, "cooldown_until": 0}


def _reserve_request(s3, bucket, context):
    try:
        requests_per_minute = float(os.environ.get("ONEMAP_REQUESTS_PER_MINUTE", "75"))
    except ValueError as error:
        raise GeocoderConfigurationError(
            "ONEMAP_REQUESTS_PER_MINUTE must be numeric"
        ) from error
    if not 1 <= requests_per_minute <= 75:
        raise GeocoderConfigurationError(
            "ONEMAP_REQUESTS_PER_MINUTE must be between 1 and 75"
        )

    state = _load_rate_state(s3, bucket)
    now = time.time()
    next_at = max(
        float(state.get("next_request_at", 0)), float(state.get("cooldown_until", 0))
    )
    wait_seconds = max(0, next_at - now)
    remaining = context.get_remaining_time_in_millis() / 1000 if context else 60
    if wait_seconds + 2 >= remaining:
        raise RetryableGeocodeError("Rate-limit wait exceeds remaining invocation time")
    if wait_seconds:
        time.sleep(wait_seconds)

    # The FIFO queue uses one message group, so this S3 timestamp serializes calls across invocations.
    _put_json(
        s3,
        bucket,
        RATE_STATE_KEY,
        {
            "next_request_at": time.time() + 60 / requests_per_minute,
            "cooldown_until": float(state.get("cooldown_until", 0)),
        },
    )


def _defer_after_throttle(s3, bucket, error, receive_count):
    state = _load_rate_state(s3, bucket)
    retry_after = _retry_after_seconds(error.retry_after, receive_count)
    until = time.time() + retry_after
    state["cooldown_until"] = max(float(state.get("cooldown_until", 0)), until)
    state["next_request_at"] = max(float(state.get("next_request_at", 0)), until)
    _put_json(s3, bucket, RATE_STATE_KEY, state)


def _valid_match(rows, postal_code):
    south, north, west, east = SINGAPORE_BOUNDS
    for row in rows:
        if (
            not isinstance(row, dict)
            or str(row.get("POSTAL", "")).zfill(6) != postal_code
        ):
            continue
        try:
            latitude = float(row["LATITUDE"])
            longitude = float(row["LONGITUDE"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            math.isfinite(latitude)
            and math.isfinite(longitude)
            and south <= latitude <= north
            and west <= longitude <= east
        ):
            return latitude, longitude
    return None


def _valid_coordinates(latitude, longitude):
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return None
    south, north, west, east = SINGAPORE_BOUNDS
    if (
        math.isfinite(latitude)
        and math.isfinite(longitude)
        and south <= latitude <= north
        and west <= longitude <= east
    ):
        return latitude, longitude
    return None


def _result_for_query(s3, bucket, query, context, receive_count):
    query_id = query["query_id"]
    postal_code = query["postal_code"]
    result_key = f"results/{query['source']}/{query['run_id']}/queries/{query_id}.json"
    try:
        result = _read_json(s3, bucket, result_key)
        if (
            result.get("schema_version") != 1
            or result.get("query_id") != query_id
            or result.get("postal_code") != postal_code
            or result.get("run_id") != query["run_id"]
            or result.get("source") != query["source"]
            or result.get("status") not in {"resolved", "unlocated"}
        ):
            raise GeocodeError("Saved query result does not match its query identity")
        if (
            result["status"] == "resolved"
            and _valid_coordinates(result.get("latitude"), result.get("longitude"))
            is None
        ):
            raise GeocodeError("Saved query result has invalid coordinates")
        if result["status"] == "unlocated" and (
            result.get("latitude") is not None or result.get("longitude") is not None
        ):
            raise GeocodeError("Saved unlocated result unexpectedly has coordinates")
        return result
    except s3.exceptions.NoSuchKey:
        pass

    cache_key = f"cache/geocoding/{query_id}.json"
    try:
        cached = _read_json(s3, bucket, cache_key)
        try:
            cache_time = datetime.fromisoformat(cached.get("geocoded_at", ""))
            cache_age = (datetime.now(UTC) - cache_time).total_seconds()
            max_age = float(os.environ.get("GEOCODE_CACHE_MAX_AGE_DAYS", "90")) * 86400
            fresh = max_age > 0 and 0 <= cache_age <= max_age
        except (TypeError, ValueError):
            fresh = False
        if (
            fresh
            and cached.get("schema_version") == 1
            and cached.get("query_id") == query_id
            and cached.get("postal_code") == postal_code
            and cached.get("status") == "resolved"
            and _valid_coordinates(cached.get("latitude"), cached.get("longitude"))
            is not None
        ):
            result = {**cached, "run_id": query["run_id"], "source": query["source"]}
            _put_json(s3, bucket, result_key, result)
            return result
    except s3.exceptions.NoSuchKey:
        pass

    coordinates = None
    matched_query = query["address"]
    for search_value in (postal_code, query["address"]):
        try:
            rows = _search(search_value, lambda: _reserve_request(s3, bucket, context))
        except _UpstreamError as error:
            if error.status == 429:
                _defer_after_throttle(s3, bucket, error, receive_count)
                raise RetryableGeocodeError(
                    "OneMap rate limited the geocoding request"
                ) from error
            if error.status >= 500:
                raise RetryableGeocodeError(str(error)) from error
            raise GeocodeError(
                f"OneMap rejected a geocoding request ({error.status})"
            ) from error
        coordinates = _valid_match(rows, postal_code)
        if coordinates:
            matched_query = search_value
            break

    now = datetime.now(UTC).isoformat()
    if coordinates:
        latitude, longitude = coordinates
        result = {
            "schema_version": 1,
            "query_id": query_id,
            "source": query["source"],
            "run_id": query["run_id"],
            "postal_code": postal_code,
            "status": "resolved",
            "latitude": latitude,
            "longitude": longitude,
            "provider": "onemap",
            "query": matched_query,
            "geocoded_at": now,
        }
        _put_json(s3, bucket, result_key, result)
        _put_json(s3, bucket, cache_key, result)
    else:
        result = {
            "schema_version": 1,
            "query_id": query_id,
            "source": query["source"],
            "run_id": query["run_id"],
            "postal_code": postal_code,
            "status": "unlocated",
            "latitude": None,
            "longitude": None,
            "provider": "onemap",
            "query": query["address"],
            "geocoded_at": now,
        }
        _put_json(s3, bucket, result_key, result)
    return result


def process_batch(message, s3, context=None, receive_count=1):
    bucket = os.environ.get("FACILITY_SYNC_BUCKET")
    if not bucket:
        raise GeocoderConfigurationError("FACILITY_SYNC_BUCKET is required")
    required = ("run_id", "source", "batch_id", "manifest_key", "batch_key")
    if (
        not isinstance(message, dict)
        or message.get("schema_version") != 1
        or any(not message.get(key) for key in required)
    ):
        raise GeocodeError("Queue message is missing required batch fields")

    try:
        run_id = str(UUID(message["run_id"]))
    except (AttributeError, TypeError, ValueError) as error:
        raise GeocodeError("Queue message has an invalid run ID") from error
    source = message["source"]
    batch_id = message["batch_id"]
    if (
        not isinstance(source, str)
        or source not in {"vet", "pet_shop"}
        or not isinstance(batch_id, str)
        or not re.fullmatch(r"batch-\d{5}", batch_id)
    ):
        raise GeocodeError("Queue message has an invalid source or batch ID")
    expected_manifest_key = f"pending/{source}/{run_id}/manifest.json"
    if message["manifest_key"] != expected_manifest_key:
        raise GeocodeError("Queue message points outside its run manifest")
    complete_key = f"results/{source}/{run_id}/batches/{batch_id}.json"
    try:
        complete = _read_json(s3, bucket, complete_key)
    except s3.exceptions.NoSuchKey:
        complete = None

    manifest = _read_json(
        s3, bucket, message["manifest_key"], message.get("manifest_version")
    )
    if (
        manifest.get("run_id") != run_id
        or manifest.get("schema_version") != 1
        or manifest.get("source") != source
        or batch_id not in manifest.get("expected_batch_ids", [])
        or manifest.get("batch_keys", {}).get(batch_id) != message["batch_key"]
        or manifest.get("batch_versions", {}).get(batch_id)
        != message.get("batch_version")
    ):
        raise GeocodeError("Queue message does not match its persisted run manifest")
    batch = _read_json(s3, bucket, message["batch_key"], message.get("batch_version"))
    if (
        batch.get("schema_version") != 1
        or batch.get("batch_id") != batch_id
        or not isinstance(batch.get("queries"), list)
    ):
        raise GeocodeError("Batch artifact is invalid")

    queries = batch["queries"]
    if not isinstance(queries, list) or not queries:
        raise GeocodeError("Batch must contain address queries")
    query_ids = []
    for query in queries:
        if (
            not isinstance(query, dict)
            or not query.get("query_id")
            or not query.get("postal_code")
            or not query.get("address")
        ):
            raise GeocodeError("Batch contains an invalid address query")
        postal_code = query["postal_code"]
        if (
            not isinstance(postal_code, str)
            or not re.fullmatch(r"\d{6}", postal_code)
            or query["query_id"]
            != hashlib.sha256(postal_code.encode("ascii")).hexdigest()
            or not isinstance(query["address"], str)
            or len(query["address"]) > 500
        ):
            raise GeocodeError("Batch query identity or address is invalid")
        query_ids.append(query["query_id"])
    if len(set(query_ids)) != len(query_ids):
        raise GeocodeError("Batch contains duplicate query identities")
    if complete is not None:
        if (
            complete.get("schema_version") == 1
            and complete.get("batch_id") == batch_id
            and complete.get("run_id") == run_id
            and complete.get("completed_query_ids") == query_ids
        ):
            run_status.emit(
                s3,
                bucket,
                source,
                run_id,
                "geocoding",
                "batch_completed",
                detail={"batch_id": batch_id},
                event_id=run_status.stable_event_id(
                    run_id, f"batch_completed:{batch_id}"
                ),
            )
            ready_key = finalize_if_complete(
                s3, bucket, source, run_id, message["manifest_key"]
            )
            if ready_key:
                complete["ready_key"] = ready_key
            return complete
        raise GeocodeError("Saved batch completion marker does not match its artifact")

    results = []
    for query in queries:
        query_result = _result_for_query(
            s3,
            bucket,
            {**query, "source": source, "run_id": run_id},
            context,
            receive_count,
        )
        results.append(query_result["query_id"])

    complete = {
        "schema_version": 1,
        "run_id": run_id,
        "source": source,
        "batch_id": batch_id,
        "completed_query_ids": results,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    _put_json(s3, bucket, complete_key, complete)
    run_status.emit(
        s3,
        bucket,
        source,
        run_id,
        "geocoding",
        "batch_completed",
        detail={"batch_id": batch_id},
        event_id=run_status.stable_event_id(run_id, f"batch_completed:{batch_id}"),
    )
    ready_key = finalize_if_complete(
        s3, bucket, source, run_id, message["manifest_key"]
    )
    if ready_key:
        complete["ready_key"] = ready_key
    return complete


def handler(event, context):
    bucket = os.environ.get("FACILITY_SYNC_BUCKET")
    if not bucket:
        raise GeocoderConfigurationError("FACILITY_SYNC_BUCKET is required")
    s3 = aws_client("s3")
    records = event.get("Records")
    if not isinstance(records, list) or not records:
        raise GeocodeError("Expected an SQS event with at least one record")
    results = []
    for record in records:
        message = None
        try:
            message = json.loads(record["body"])
            receive_count = int(
                record.get("attributes", {}).get("ApproximateReceiveCount", "1")
            )
            if run_status.read_json(
                s3, bucket, f"failed/{message['source']}/{message['run_id']}.json"
            ):
                results.append({"run_id": message["run_id"], "status": "failed"})
                continue
            results.append(process_batch(message, s3, context, receive_count))
        except Exception as error:
            receive_count = int(
                record.get("attributes", {}).get("ApproximateReceiveCount", "1")
            )
            permanent = isinstance(
                error, (GeocodeError, ValueError, KeyError, TypeError)
            ) and not isinstance(error, RetryableGeocodeError)
            if permanent:
                run_status.put_json(
                    s3,
                    bucket,
                    f"quarantine/{record.get('messageId', 'unknown')}.json",
                    {
                        "body": record.get("body", ""),
                        "error_code": type(error).__name__,
                    },
                )
                run_status.metric("QuarantinedMessages", 1)
            try:
                if isinstance(message, dict):
                    source, run_id = run_status.identity(
                        message.get("source"), message.get("run_id")
                    )
                    run_status.fail(
                        s3,
                        bucket,
                        source,
                        run_id,
                        "geocoding",
                        type(error).__name__,
                        permanent=permanent or receive_count >= 5,
                        batch_id=message.get("batch_id"),
                    )
            except Exception:
                import logging

                logging.getLogger(__name__).error("Could not persist geocoding failure")
                raise
            if permanent:
                results.append({"status": "quarantined"})
                continue
            if record.get("receiptHandle") and os.environ.get("GEOCODE_QUEUE_URL"):
                state = _load_rate_state(s3, bucket)
                delay = max(
                    _retry_after_seconds(None, receive_count),
                    int(float(state.get("cooldown_until", 0)) - time.time()) + 1,
                )
                aws_client("sqs").change_message_visibility(
                    QueueUrl=os.environ["GEOCODE_QUEUE_URL"],
                    ReceiptHandle=record["receiptHandle"],
                    VisibilityTimeout=min(43200, max(1, delay)),
                )
            raise
    return {"processed_batches": len(results), "results": results}
