import json
import re
from datetime import UTC, datetime

from facilities.ingestion.status import create_json, digest


class SnapshotError(ValueError):
    pass


def _read_json(s3, bucket, key, version=None):
    params = {"Bucket": bucket, "Key": key}
    if version:
        params["VersionId"] = version
    return json.loads(s3.get_object(**params)["Body"].read())


def finalize_if_complete(s3, bucket, source, run_id, manifest_key):
    if (
        source not in {"vet", "pet_shop"}
        or manifest_key != f"pending/{source}/{run_id}/manifest.json"
    ):
        raise SnapshotError("Invalid snapshot identity")
    manifest = _read_json(s3, bucket, manifest_key)
    if (
        manifest.get("schema_version") != 1
        or manifest.get("source") != source
        or manifest.get("run_id") != run_id
    ):
        raise SnapshotError("Run manifest identity is invalid")

    ready_key = f"ready/{source}/{run_id}.json"
    try:
        existing = _read_json(s3, bucket, ready_key)
    except s3.exceptions.NoSuchKey:
        existing = None
    if existing is not None:
        existing_digest = existing.get("snapshot_sha256")
        content = dict(existing)
        content.pop("snapshot_sha256", None)
        actual_digest = digest(content)
        if (
            existing.get("run_id") != run_id
            or existing.get("source") != source
            or existing.get("document_sha256") != manifest.get("document_sha256")
            or existing_digest != actual_digest
        ):
            raise SnapshotError("Existing ready artifact conflicts with this run")
        return ready_key

    expected_batches = manifest.get("expected_batch_ids")
    if (
        not isinstance(expected_batches, list)
        or not expected_batches
        or len(set(expected_batches)) != len(expected_batches)
    ):
        raise SnapshotError("Run manifest has no expected geocoding batches")
    query_results = {}
    for batch_id in expected_batches:
        batch_key = manifest.get("batch_keys", {}).get(batch_id)
        if not batch_key:
            raise SnapshotError("Run manifest is missing an expected batch artifact")
        batch = _read_json(
            s3,
            bucket,
            batch_key,
            manifest.get("batch_versions", {}).get(batch_id),
        )
        if batch.get("schema_version") != 1 or batch.get("batch_id") != batch_id:
            raise SnapshotError("Batch artifact does not match the manifest")
        complete_key = f"results/{source}/{run_id}/batches/{batch_id}.json"
        try:
            complete = _read_json(s3, bucket, complete_key)
        except s3.exceptions.NoSuchKey:
            return None
        expected_query_ids = [
            query.get("query_id") for query in batch.get("queries", [])
        ]
        if (
            complete.get("schema_version") != 1
            or complete.get("run_id") != run_id
            or complete.get("batch_id") != batch_id
            or complete.get("completed_query_ids") != expected_query_ids
        ):
            raise SnapshotError(
                "A geocoding batch is not complete or has invalid results"
            )
        for query in batch["queries"]:
            query_id = query["query_id"]
            result_key = f"results/{source}/{run_id}/queries/{query_id}.json"
            result = _read_json(s3, bucket, result_key)
            if (
                result.get("schema_version") != 1
                or result.get("query_id") != query_id
                or result.get("postal_code") != query.get("postal_code")
                or result.get("run_id") != run_id
                or result.get("source") != source
                or result.get("status") not in {"resolved", "unlocated"}
            ):
                raise SnapshotError("A saved geocoding result is invalid")
            if result["status"] == "resolved":
                try:
                    latitude, longitude = (
                        float(result["latitude"]),
                        float(result["longitude"]),
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise SnapshotError(
                        "A resolved result has invalid coordinates"
                    ) from error
                if not (1.15 <= latitude <= 1.5 and 103.55 <= longitude <= 104.15):
                    raise SnapshotError("A resolved result is outside Singapore")
            elif (
                result.get("latitude") is not None
                or result.get("longitude") is not None
            ):
                raise SnapshotError("An unlocated result unexpectedly has coordinates")
            if query_id in query_results:
                raise SnapshotError("Run contains a duplicate geocoding query")
            query_results[query_id] = result

    parsed = _read_json(s3, bucket, manifest["parsed_key"])
    records = parsed.get("records")
    if (
        parsed.get("schema_version") != 1
        or parsed.get("run_id") != run_id
        or parsed.get("source") != source
        or not isinstance(records, list)
        or len(records) != parsed.get("parsed_count")
        or not records
    ):
        raise SnapshotError("Parsed registry artifact is invalid")

    source_keys = set()
    record_query_ids = set()
    output_records = []
    for record in records:
        source_key = record.get("source_key")
        query_id = record.get("geocode_query_id")
        if (
            record.get("source_id") != source
            or record.get("facility_type") != source
            or not isinstance(source_key, str)
            or not source_key
            or len(source_key) > 64
            or source_key in source_keys
            or not isinstance(record.get("name"), str)
            or not record["name"].strip()
            or not re.fullmatch(r"\d{6}", str(record.get("postal_code", "")))
            or not query_id
            or query_id not in query_results
        ):
            raise SnapshotError("Parsed facility record failed validation")
        source_keys.add(source_key)
        record_query_ids.add(query_id)
        location = query_results[query_id]
        output_records.append(
            {
                **record,
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "geocode_status": location["status"],
                "geocode_query": location["query"],
                "geocode_provider": location["provider"],
                "geocoded_at": location["geocoded_at"],
            }
        )
    if record_query_ids != set(query_results) or len(query_results) != manifest.get(
        "expected_query_count"
    ):
        raise SnapshotError("Geocoding results do not match the parsed registry")

    snapshot = {
        "schema_version": 1,
        "parser_version": parsed.get("parser_version"),
        "run_id": run_id,
        "source": source,
        "facility_type": source,
        "registry_url": parsed["registry_url"],
        "document_url": parsed["document_url"],
        "document_sha256": parsed["document_sha256"],
        "raw_key": parsed["raw_key"],
        "source_published_at": parsed.get("source_published_at"),
        "checked_at": parsed.get("retrieved_at") or datetime.now(UTC).isoformat(),
        "expected_record_count": len(output_records),
        "unlocated_count": sum(
            record["geocode_status"] == "unlocated" for record in output_records
        ),
        "records": output_records,
    }
    if snapshot["document_sha256"] != manifest.get("document_sha256"):
        raise SnapshotError("Parsed PDF hash does not match the run manifest")
    snapshot["snapshot_sha256"] = digest(snapshot)
    if not create_json(s3, bucket, ready_key, snapshot):
        return finalize_if_complete(s3, bucket, source, run_id, manifest_key)
    return ready_key
