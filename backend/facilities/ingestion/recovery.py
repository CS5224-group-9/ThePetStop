"""Bounded repair of interrupted runs; no database or live-source bypass."""

import json
import os
import time
from datetime import datetime
from uuid import uuid4

from facilities.ingestion import status
from facilities.ingestion.aws import client
from facilities.ingestion.dispatch import MESSAGE_GROUP
from facilities.ingestion.fetch import handler as fetch
from facilities.ingestion.finalize import finalize_if_complete


def keys(s3, bucket, prefix):
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=prefix
    ):
        for item in page.get("Contents", []):
            yield item["Key"]


def replay(s3, bucket, key):
    value = status.read_json(s3, bucket, key)
    if value is not None:
        status.put_json(s3, bucket, key, value)


def replay_status(s3, bucket, source, run_id):
    for key in keys(s3, bucket, f"status/{source}/{run_id}/"):
        event_id = key.rsplit("/", 1)[-1]
        if (
            status.read_json(s3, bucket, f"projected/{source}/{run_id}/{event_id}")
            is None
        ):
            replay(s3, bucket, key)


def repair_run(s3, sqs, bucket, source, run_id, *, force=False):
    if force:
        s3.delete_object(Bucket=bucket, Key=f"failed/{source}/{run_id}.json")
    if status.read_json(s3, bucket, f"loaded/{source}/{run_id}.json"):
        replay_status(s3, bucket, source, run_id)
        return "loaded"
    if status.read_json(s3, bucket, f"failed/{source}/{run_id}.json"):
        replay_status(s3, bucket, source, run_id)
        return "failed"
    control = status.read_json(s3, bucket, f"control/{source}/{run_id}.json")
    if control is None:
        raise ValueError("Run has no control artifact")
    previous = status.read_json(s3, bucket, f"recovery/{source}/{run_id}.json") or {}
    started = max(
        datetime.fromisoformat(control["started_at"]).timestamp(),
        previous.get("resumed_at", 0),
    )
    age = time.time() - started
    if not force and age < 900 and not previous:
        return "waiting"
    if (
        not force
        and age > float(os.environ.get("FACILITY_MAX_RUN_AGE_HOURS", "24")) * 3600
    ):
        status.fail(s3, bucket, source, run_id, "queued", "stalled_run", permanent=True)
        return "expired"
    cooldown = status.read_json(s3, bucket, f"deferred/{source}/{run_id}.json")
    if cooldown and cooldown["until"] > time.time():
        return "waiting"
    if not force and time.time() - previous.get("attempted_at", 0) < 900:
        return "waiting"
    completed = len(list(keys(s3, bucket, f"results/{source}/{run_id}/batches/")))
    progressing = completed > previous.get("completed", 0)
    attempts = 0 if force or progressing else previous.get("attempts", 0) + 1
    if attempts > 5 and not force:
        status.fail(
            s3, bucket, source, run_id, "queued", "recovery_exhausted", permanent=True
        )
        return "failed"
    status.put_json(
        s3,
        bucket,
        f"recovery/{source}/{run_id}.json",
        {
            "attempts": attempts,
            "attempted_at": time.time(),
            "completed": completed,
            "resumed_at": time.time() if force else previous.get("resumed_at", 0),
        },
    )
    manifest_key = f"pending/{source}/{run_id}/manifest.json"
    manifest = status.read_json(s3, bucket, manifest_key)
    if manifest is None:
        if force:
            status.emit(s3, bucket, source, run_id, "queued", "resumed")
        fetch({"operation": "start", "source": source, "run_id": run_id}, None)
        return "fetch_resumed"
    ready = finalize_if_complete(s3, bucket, source, run_id, manifest_key)
    if ready:
        # Prioritize data delivery; repair status history after the load receipt exists.
        replay(s3, bucket, ready)
        if force:
            status.emit(s3, bucket, source, run_id, "queued", "resumed")
        return "load_replayed"
    if force:
        status.emit(s3, bucket, source, run_id, "queued", "resumed")
    replay_status(s3, bucket, source, run_id)
    if progressing and not force:
        return "progressing"
    for batch_id in manifest["expected_batch_ids"]:
        if status.read_json(
            s3, bucket, f"results/{source}/{run_id}/batches/{batch_id}.json"
        ):
            continue
        message = {
            "schema_version": 1,
            "run_id": run_id,
            "source": source,
            "batch_id": batch_id,
            "manifest_key": manifest_key,
            "batch_key": manifest["batch_keys"][batch_id],
            "batch_version": manifest["batch_versions"].get(batch_id),
        }
        sqs.send_message(
            QueueUrl=os.environ["GEOCODE_QUEUE_URL"],
            MessageBody=json.dumps(message),
            MessageGroupId=MESSAGE_GROUP,
            MessageDeduplicationId=str(uuid4()),
        )
    status.emit(
        s3, bucket, source, run_id, "queued", "reconciled", detail={"attempt": attempts}
    )
    return "work_requeued"


def handler(event, context):
    s3, sqs = client("s3"), client("sqs")
    bucket = os.environ["FACILITY_SYNC_BUCKET"]
    for source in status.SOURCES:
        dates = [
            row.get("checked_at")
            for key in keys(s3, bucket, f"loaded/{source}/")
            if (row := status.read_json(s3, bucket, key))
            and row.get("status") == "succeeded"
            and row.get("checked_at")
        ]
        age = (
            max(
                0,
                (
                    time.time()
                    - max(datetime.fromisoformat(value).timestamp() for value in dates)
                )
                / 3600,
            )
            if dates
            else 100000
        )
        print(
            json.dumps(
                {
                    "_aws": {
                        "Timestamp": int(time.time() * 1000),
                        "CloudWatchMetrics": [
                            {
                                "Namespace": "PetStop/FacilityIngestion",
                                "Dimensions": [["source"]],
                                "Metrics": [{"Name": "DataAgeHours", "Unit": "None"}],
                            }
                        ],
                    },
                    "source": source,
                    "DataAgeHours": age,
                }
            )
        )
    if os.environ.get("GEOCODE_DLQ_URL"):
        dead = sqs.receive_message(
            QueueUrl=os.environ["GEOCODE_DLQ_URL"],
            MaxNumberOfMessages=10,
            VisibilityTimeout=30,
        ).get("Messages", [])
        for item in dead:
            status.put_json(
                s3,
                bucket,
                f"work-failures/{item['MessageId']}.json",
                {"body": item["Body"], "message_id": item["MessageId"]},
            )
            try:
                message = json.loads(item["Body"])
                source, run_id = status.identity(message["source"], message["run_id"])
            except (ValueError, TypeError, KeyError):
                status.metric("QuarantinedMessages", 1)
            else:
                status.fail(
                    s3,
                    bucket,
                    source,
                    run_id,
                    "geocoding",
                    "work_dlq",
                    permanent=True,
                    batch_id=message.get("batch_id"),
                )
            sqs.delete_message(
                QueueUrl=os.environ["GEOCODE_DLQ_URL"],
                ReceiptHandle=item["ReceiptHandle"],
            )
    if event.get("run_id"):
        source, run_id = status.identity(event.get("source"), event["run_id"])
        return {
            "result": repair_run(
                s3, sqs, bucket, source, run_id, force=event.get("operation") == "retry"
            )
        }
    results = []
    for key in keys(s3, bucket, "control/"):
        if context and context.get_remaining_time_in_millis() < 30000:
            break
        control = status.read_json(s3, bucket, key)
        try:
            results.append(
                repair_run(
                    s3,
                    sqs,
                    bucket,
                    *status.identity(control["source"], control["run_id"]),
                )
            )
        except Exception as error:
            status.fail(
                s3,
                bucket,
                control["source"],
                control["run_id"],
                "queued",
                type(error).__name__,
            )
    return {"runs_checked": len(results), "results": results}


def failure_handler(event, context):
    s3 = client("s3")
    bucket = os.environ["FACILITY_SYNC_BUCKET"]
    for record in event["Records"]:
        envelope = json.loads(record["body"])
        status.put_json(
            s3, bucket, f"invocation-failures/{record['messageId']}.json", envelope
        )
        payload = envelope.get("requestPayload", envelope)
        if payload.get("source") in status.SOURCES and payload.get("run_id"):
            status.fail(
                s3,
                bucket,
                payload["source"],
                payload["run_id"],
                "fetching",
                "async_retries_exhausted",
                permanent=False,
            )
        else:
            for item in payload.get("Records", []):
                key = item.get("s3", {}).get("object", {}).get("key", "")
                parts = key.split("/")
                if len(parts) == 3 and parts[0] == "ready":
                    source, run_id = status.identity(
                        parts[1], parts[2].removesuffix(".json")
                    )
                    status.fail(
                        s3, bucket, source, run_id, "loading", "async_retries_exhausted"
                    )
    return {"recorded": len(event["Records"])}
