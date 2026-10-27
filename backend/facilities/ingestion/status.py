"""Durable status events; producers never need a database connection."""

import hashlib
import json
import logging
import re
import time
from datetime import UTC, datetime
from functools import wraps
from uuid import UUID, uuid4

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
SOURCES = {"vet", "pet_shop"}
STAGES = {"fetching", "parsing", "queued", "geocoding", "loading", "complete"}
STAGE_ORDER = {
    name: number
    for number, name in enumerate(
        ("fetching", "parsing", "queued", "geocoding", "loading", "complete")
    )
}


def identity(source, run_id):
    if source not in SOURCES or str(UUID(str(run_id))) != str(run_id):
        raise ValueError("Invalid ingestion run identity")
    return source, str(run_id)


def metric(name, value):
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "PetStop/FacilityIngestion",
                            "Dimensions": [[]],
                            "Metrics": [{"Name": name}],
                        }
                    ],
                },
                name: value,
            }
        )
    )


def read_json(s3, bucket, key):
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read(20 * 1024 * 1024 + 1)
        if len(body) > 20 * 1024 * 1024:
            raise ValueError("Ingestion artifact exceeds size limit")
        return json.loads(body)
    except s3.exceptions.NoSuchKey:
        return None


def put_json(s3, bucket, key, value, **conditions):
    return s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
        ContentType="application/json",
        **conditions,
    )


def create_json(s3, bucket, key, value):
    try:
        put_json(s3, bucket, key, value, IfNoneMatch="*")
        return True
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
            raise
        return False


def begin(s3, bucket, source, run_id):
    identity(source, run_id)
    key = f"control/{source}/{run_id}.json"
    control = {
        "schema_version": 1,
        "source": source,
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
    }
    create_json(s3, bucket, key, control)
    control = read_json(s3, bucket, key)
    emit(s3, bucket, source, run_id, "fetching", "started", event_id=run_id)
    return control


def emit(s3, bucket, source, run_id, stage, kind, *, detail=None, event_id=None):
    identity(source, run_id)
    if stage not in STAGES:
        raise ValueError("Invalid ingestion stage")
    event_id = str(UUID(str(event_id))) if event_id else str(uuid4())
    event = {
        "schema_version": 1,
        "event_id": event_id,
        "source": source,
        "run_id": run_id,
        "stage": stage,
        "kind": kind,
        "occurred_at": datetime.now(UTC).isoformat(),
        "detail": detail or {},
    }
    created = create_json(
        s3, bucket, f"status/{source}/{run_id}/{event_id}.json", event
    )
    logger.info(json.dumps({"event": "facility_ingestion", **event}))
    if created and kind == "failed":
        print(
            json.dumps(
                {
                    "_aws": {
                        "Timestamp": int(time.time() * 1000),
                        "CloudWatchMetrics": [
                            {
                                "Namespace": "PetStop/FacilityIngestion",
                                "Dimensions": [["source"]],
                                "Metrics": [{"Name": "Failures", "Unit": "Count"}],
                            }
                        ],
                    },
                    "source": source,
                    "Failures": 1,
                }
            )
        )
    return event


def fail(s3, bucket, source, run_id, stage, code, *, permanent=False, batch_id=None):
    detail = {"error_code": code, "permanent": permanent}
    if isinstance(batch_id, str) and re.fullmatch(r"batch-\d{5}", batch_id):
        detail["batch_id"] = batch_id
    if permanent:
        create_json(
            s3,
            bucket,
            f"failed/{source}/{run_id}.json",
            {"source": source, "run_id": run_id, **detail},
        )
    emit(
        s3,
        bucket,
        source,
        run_id,
        stage,
        "failed" if permanent else "retrying",
        detail=detail,
    )


def project(event):
    """Project immutable events idempotently, including out-of-order delivery."""
    from django.db import transaction
    from django.utils.dateparse import parse_datetime

    from facilities.models import FacilitySyncEvent, FacilitySyncRun

    if not isinstance(event, dict) or event.get("schema_version") != 1:
        raise ValueError("Invalid ingestion status event")
    source, run_id = identity(event.get("source"), event.get("run_id"))
    event_id = UUID(event["event_id"])
    occurred = parse_datetime(event["occurred_at"])
    stage, kind, detail = event["stage"], event["kind"], event["detail"]
    if (
        occurred is None
        or occurred.tzinfo is None
        or stage not in STAGES
        or not isinstance(kind, str)
        or len(kind) > 48
        or not isinstance(detail, dict)
    ):
        raise ValueError("Invalid ingestion event fields")
    with transaction.atomic():
        run, _ = FacilitySyncRun.objects.get_or_create(
            run_id=run_id, defaults={"source": source, "started_at": occurred}
        )
        run = FacilitySyncRun.objects.select_for_update().get(pk=run.pk)
        if run.source != source:
            raise ValueError("Status source does not match its run")
        _, created = FacilitySyncEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                "run": run,
                "stage": stage,
                "kind": kind,
                "detail": detail,
                "occurred_at": occurred,
            },
        )
        if not created:
            return
        run.started_at = min(run.started_at, occurred)
        if kind == "batch_completed":
            run.completed_batch_count = run.events.filter(
                kind="batch_completed"
            ).count()
        if kind == "retrying":
            run.retry_count += 1
        if "batch_count" in detail:
            count = int(detail["batch_count"])
            if not 1 <= count <= 10000:
                raise ValueError("Invalid expected batch count")
            run.expected_batch_count = max(run.expected_batch_count, count)
        terminal = run.status in {"succeeded", "superseded", "review_required"}
        if not terminal and (
            run.last_activity_at is None or occurred >= run.last_activity_at
        ):
            if STAGE_ORDER[stage] >= STAGE_ORDER.get(run.stage, 0) or kind == "resumed":
                run.stage = stage
            run.last_activity_at = occurred
            if kind == "failed":
                run.status = "failed"
                run.error_code = str(detail.get("error_code", "stage_failed"))[:64]
                run.finished_at = occurred
            elif run.status != "failed" or kind == "resumed":
                run.status = "running"
                if kind == "resumed":
                    run.finished_at = None
                    run.error_code = ""
                    run.error_message = ""
            if "parsed_count" in detail:
                run.parsed_count = int(detail["parsed_count"])
        run.save()


def stable_event_id(run_id, name):
    from uuid import uuid5

    return str(uuid5(UUID(run_id), name))


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def serialized(handler):
    """A conditional lease prevents two fetch/recovery invocations changing a manifest."""

    @wraps(handler)
    def wrapped(event, context):
        import os
        from uuid import NAMESPACE_URL, uuid5

        from facilities.ingestion.aws import client

        event = dict(event)
        if not event.get("run_id"):
            event["run_id"] = (
                str(uuid5(NAMESPACE_URL, str(event["execution_id"])))
                if event.get("execution_id")
                else str(uuid4())
            )
        source, run_id = identity(event.get("source"), event["run_id"])
        s3, bucket = client("s3"), os.environ["FACILITY_SYNC_BUCKET"]
        key = f"leases/{source}/{run_id}.json"
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            lease = json.loads(obj["Body"].read())
            if lease["expires_at"] > time.time():
                raise RuntimeError("This run is already being fetched or dispatched")
            condition = {"IfMatch": obj["ETag"]}
        except s3.exceptions.NoSuchKey:
            condition = {"IfNoneMatch": "*"}
        response = put_json(
            s3, bucket, key, {"expires_at": time.time() + 300}, **condition
        )
        try:
            return handler(event, context)
        finally:
            try:
                put_json(s3, bucket, key, {"expires_at": 0}, IfMatch=response["ETag"])
            except Exception:
                logger.error(
                    "Could not release ingestion lease", extra={"run_id": run_id}
                )

    return wrapped
