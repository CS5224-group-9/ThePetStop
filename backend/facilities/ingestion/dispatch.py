import hashlib
import json
import os

MESSAGE_GROUP = "onemap-geocoding"


def make_batches(records, batch_size):
    queries = {}
    for record in records:
        postal_code = record["postal_code"]
        query_id = hashlib.sha256(postal_code.encode("ascii")).hexdigest()
        record["geocode_query_id"] = query_id
        queries.setdefault(
            query_id,
            {"query_id": query_id, "postal_code": postal_code, "address": record["address"]},
        )

    ordered_queries = [queries[key] for key in sorted(queries)]
    batches = []
    for start in range(0, len(ordered_queries), batch_size):
        batch_id = f"batch-{start // batch_size:05d}"
        batches.append(
            {
                "schema_version": 1,
                "batch_id": batch_id,
                "queries": ordered_queries[start : start + batch_size],
            }
        )
    return batches


def create_batch_artifacts(s3, bucket, source, run_id, records, batch_size):
    batches = make_batches(records, batch_size)
    batch_keys = {}
    batch_versions = {}
    for batch in batches:
        key = f"pending/{source}/{run_id}/batches/{batch['batch_id']}.json"
        batch_keys[batch["batch_id"]] = key
        response = s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(batch, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json",
        )
        batch_versions[batch["batch_id"]] = response.get("VersionId")
    return batches, batch_keys, batch_versions


def dispatch_batches(
    s3,
    sqs,
    queue_url,
    bucket,
    source,
    run_id,
    parsed_key,
    document_sha256,
    batches,
    batch_keys,
    batch_versions,
):
    manifest_key = f"pending/{source}/{run_id}/manifest.json"
    expected_ids = [batch["batch_id"] for batch in batches]
    try:
        existing = json.loads(
            s3.get_object(Bucket=bucket, Key=manifest_key)["Body"].read()
        )
        dispatched = set(existing["dispatched_batch_ids"])
        if existing["expected_batch_ids"] != expected_ids:
            raise ValueError("Existing run manifest does not match the parsed batches")
        if existing["document_sha256"] != document_sha256:
            raise ValueError("A run ID cannot be reused for a different registry PDF")
        if existing["batch_versions"] != batch_versions:
            raise ValueError("Existing run batch versions do not match")
    except s3.exceptions.NoSuchKey:
        dispatched = set()

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "source": source,
        "parsed_key": parsed_key,
        "document_sha256": document_sha256,
        "expected_query_count": sum(len(batch["queries"]) for batch in batches),
        "expected_batch_ids": expected_ids,
        "batch_keys": batch_keys,
        "batch_versions": batch_versions,
        "dispatched_batch_ids": sorted(dispatched),
    }

    def save_manifest():
        response = s3.put_object(
            Bucket=bucket,
            Key=manifest_key,
            Body=json.dumps(manifest, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json",
        )
        return response.get("VersionId")

    manifest_version = save_manifest()
    for batch in batches:
        batch_id = batch["batch_id"]
        if batch_id in dispatched:
            continue
        message = {
            "schema_version": 1,
            "run_id": run_id,
            "source": source,
            "batch_id": batch_id,
            "manifest_key": manifest_key,
            "manifest_version": manifest_version,
            "batch_key": batch_keys[batch_id],
            "batch_version": batch_versions[batch_id],
        }
        dedup_id = hashlib.sha256(f"{run_id}:{batch_id}".encode()).hexdigest()
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message, separators=(",", ":")),
            MessageGroupId=MESSAGE_GROUP,
            MessageDeduplicationId=dedup_id,
        )
        dispatched.add(batch_id)
        manifest["dispatched_batch_ids"] = sorted(dispatched)
        manifest_version = save_manifest()
    return manifest_key


def resume_dispatch(s3, sqs, queue_url, bucket, source, run_id):
    manifest_key = f"pending/{source}/{run_id}/manifest.json"
    manifest_object = s3.get_object(Bucket=bucket, Key=manifest_key)
    manifest = json.loads(manifest_object["Body"].read())
    if manifest.get("run_id") != run_id or manifest.get("source") != source:
        raise ValueError("Run manifest identity does not match the dispatch request")
    batches = []
    for batch_id in manifest["expected_batch_ids"]:
        params = {"Bucket": bucket, "Key": manifest["batch_keys"][batch_id]}
        version = manifest["batch_versions"].get(batch_id)
        if version:
            params["VersionId"] = version
        batches.append(json.loads(s3.get_object(**params)["Body"].read()))
    dispatch_batches(
        s3,
        sqs,
        queue_url,
        bucket,
        source,
        run_id,
        manifest["parsed_key"],
        manifest["document_sha256"],
        batches,
        manifest["batch_keys"],
        manifest["batch_versions"],
    )
    return {"run_id": run_id, "source": source, "batch_count": len(batches)}


def batch_size_from_environment():
    try:
        size = int(os.environ.get("GEOCODE_BATCH_MAX_REQUESTS", "10"))
    except ValueError as error:
        raise ValueError("GEOCODE_BATCH_MAX_REQUESTS must be an integer") from error
    if not 1 <= size <= 100:
        raise ValueError("GEOCODE_BATCH_MAX_REQUESTS must be between 1 and 100")
    return size
