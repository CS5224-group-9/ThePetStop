"""Exercise Floci event delivery and failure recovery against the isolated fixture DB."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

import boto3
import psycopg
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[2]
BUCKET = "petstop-facility-sync-fixture"
DSN = "postgresql://petstop:petstop@localhost:5434/petstop_ingestion_test"
session = boto3.Session(
    aws_access_key_id="test", aws_secret_access_key="test", region_name="ap-southeast-1"
)
s3 = session.client(
    "s3",
    endpoint_url="http://localhost:4566",
    config=Config(connect_timeout=3, read_timeout=10, s3={"addressing_style": "path"}),
)


def close_connection(request, **kwargs):
    request.headers["Connection"] = "close"


s3.meta.events.register("before-sign.s3", close_connection)
lambdas = session.client(
    "lambda",
    endpoint_url="http://localhost:4566",
    config=Config(connect_timeout=3, read_timeout=190, retries={"max_attempts": 0}),
)


def invoke(stage, payload):
    result = lambdas.invoke(
        FunctionName=f"petstop-facility-{stage}-fixture",
        Payload=json.dumps(payload).encode(),
    )
    value = json.loads(result["Payload"].read())
    if result.get("FunctionError"):
        raise RuntimeError(f"{stage}: {value.get('errorType', 'unknown_error')}")
    return value


def wait_until(check, description, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(2)
    raise TimeoutError(f"Timed out: {description}")


def sql(query, params=()):
    with psycopg.connect(DSN, connect_timeout=5) as conn:
        return conn.execute(query, params).fetchall()


def run_state(run_id):
    rows = sql(
        "select status from facilities_facilitysyncrun where run_id=%s", (run_id,)
    )
    return rows[0][0] if rows else None


def scenario(name):
    request = Request(
        "http://localhost:8080/scenario",
        data=json.dumps({"name": name}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        response.read()
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=BUCKET, Prefix="cache/"
    ):
        for obj in page.get("Contents", []):
            s3.delete_object(Bucket=BUCKET, Key=obj["Key"])


def configure(stage, environment):
    name = f"petstop-facility-{stage}-fixture"
    lambdas.update_function_configuration(
        FunctionName=name, Environment={"Variables": environment}
    )
    wait_until(
        lambda: (
            lambdas.get_function_configuration(FunctionName=name).get(
                "LastUpdateStatus"
            )
            in (None, "Successful")
        ),
        "function update",
    )


def object_exists(key):
    try:
        s3.get_object(Bucket=BUCKET, Key=key)
        return True
    except s3.exceptions.NoSuchKey:
        return False


def check_conditions():
    key = f"coordination/conditional-check-{uuid4()}.json"
    first = s3.put_object(Bucket=BUCKET, Key=key, Body=b"first", IfNoneMatch="*")
    other = s3.put_object(Bucket=BUCKET, Key=f"{key}.other", Body=b"other")
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"first", IfMatch=first["ETag"])
    for condition in ({"IfNoneMatch": "*"}, {"IfMatch": other["ETag"]}):
        try:
            s3.put_object(Bucket=BUCKET, Key=key, Body=b"second", **condition)
        except ClientError as error:
            code = error.response["Error"]["Code"]
            allowed = {"PreconditionFailed", "412"}
            current = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            if code not in allowed or current != b"first":
                raise RuntimeError(
                    f"Conditional check {next(iter(condition))}: {code}; original body preserved={current == b'first'}"
                ) from error
        else:
            raise RuntimeError("Floci did not enforce conditional S3 writes")
    s3.delete_object(Bucket=BUCKET, Key=key)
    s3.delete_object(Bucket=BUCKET, Key=f"{key}.other")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset-queues",
        action="store_true",
        help="Purge only this suite's fixture queues before running; run suites serially",
    )
    args = parser.parse_args()
    check_conditions()
    if args.reset_queues:
        sqs = session.client("sqs", endpoint_url="http://localhost:4566")
        for name in (
            "petstop-geocode-fixture.fifo",
            "petstop-geocode-fixture-dlq.fifo",
            "petstop-facility-invocation-failures-fixture",
        ):
            url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
            sqs.purge_queue(QueueUrl=url)
    environment = {
        **os.environ,
        "DATABASE_URL": DSN,
        "DJANGO_SECRET_KEY": "fixture-only",
    }
    subprocess.run(
        [sys.executable, str(ROOT / "backend/manage.py"), "migrate", "--noinput"],
        env=environment,
        check=True,
    )
    runs = {}
    for name in ("happy", "throttle", "expired"):
        scenario(name)
        if name == "expired":
            config = lambdas.get_function_configuration(
                FunctionName="petstop-facility-geocode-fixture"
            )["Environment"]["Variables"]
            configure(
                "geocode",
                {
                    **config,
                    "ONEMAP_ACCESS_TOKEN": "fixture-expired",
                    "FIXTURE_RUN_ID": str(uuid4()),
                },
            )
        for source in ("vet", "pet_shop"):
            run_id = str(uuid4())
            print(f"{name}: {source} {run_id}", flush=True)
            invoke("fetch", {"operation": "start", "source": source, "run_id": run_id})
            wait_until(
                lambda run_id=run_id: (
                    run_state(run_id) in {"succeeded", "failed", "review_required"}
                ),
                "terminal run status",
            )
            if run_state(run_id) != "succeeded":
                raise RuntimeError(f"Fixture run failed: {run_id}")
            if name == "happy":
                key = f"control/{source}/{run_id}.json"
                before_control = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
                invoke(
                    "fetch", {"operation": "start", "source": source, "run_id": run_id}
                )
                if (
                    s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
                    != before_control
                ):
                    raise RuntimeError(
                        "Duplicate start replaced the stable run control"
                    )
            runs[source] = run_id
        expected = [
            ("FIXTURE SHOP A",),
            ("FIXTURE SHOP B",),
            ("FIXTURE VET A",),
            ("FIXTURE VET B",),
        ]
        if (
            sql("select name from facilities_facility where active order by name")
            != expected
        ):
            raise RuntimeError(
                "Fixture facilities differ from the reviewed expected dataset"
            )

    before = sql("select id from facilities_facility order by id")
    scenario("malformed")
    run_id = str(uuid4())
    print(f"malformed: vet {run_id}", flush=True)
    try:
        invoke("fetch", {"operation": "start", "source": "vet", "run_id": run_id})
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Malformed PDF unexpectedly succeeded")
    invoke("reconcile", {"source": "vet", "run_id": run_id})
    wait_until(lambda: run_state(run_id) == "failed", "malformed PDF failure status")
    if sql("select id from facilities_facility order by id") != before:
        raise RuntimeError("Failed PDF changed the last good dataset")
    scenario("happy")
    run_id = runs["vet"]
    print(f"database outage and replay: vet {run_id}", flush=True)
    ready_key = f"ready/vet/{run_id}.json"
    loaded_key = f"loaded/vet/{run_id}.json"
    loader = lambdas.get_function_configuration(
        FunctionName="petstop-facility-load-fixture"
    )["Environment"]["Variables"]
    configure(
        "load",
        {
            **loader,
            "DATABASE_URL": "postgresql://petstop:petstop@127.0.0.1:1/petstop_ingestion_test",
        },
    )
    try:
        s3.delete_object(Bucket=BUCKET, Key=loaded_key)
        body = s3.get_object(Bucket=BUCKET, Key=ready_key)["Body"].read()
        s3.put_object(
            Bucket=BUCKET, Key=ready_key, Body=body, ContentType="application/json"
        )

        def recorded_outage():
            for page in s3.get_paginator("list_objects_v2").paginate(
                Bucket=BUCKET, Prefix=f"status/vet/{run_id}/"
            ):
                for obj in page.get("Contents", []):
                    event = json.loads(
                        s3.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read()
                    )
                    if event["stage"] == "loading" and event["kind"] == "retrying":
                        return True
            return False

        wait_until(recorded_outage, "durable database outage event")
    finally:
        configure("load", loader)
    invoke("reconcile", {"operation": "retry", "source": "vet", "run_id": run_id})
    wait_until(lambda: object_exists(loaded_key), "recovered load receipt")
    if sql("select id from facilities_facility order by id") != before:
        raise RuntimeError(
            "Duplicate delivery or outage recovery changed facility identity"
        )
    sqs = session.client("sqs", endpoint_url="http://localhost:4566")
    failed_run = str(uuid4())
    print(f"dead-letter archive: vet {failed_run}", flush=True)
    from datetime import UTC, datetime

    s3.put_object(
        Bucket=BUCKET,
        Key=f"control/vet/{failed_run}.json",
        Body=json.dumps(
            {
                "schema_version": 1,
                "source": "vet",
                "run_id": failed_run,
                "started_at": datetime.now(UTC).isoformat(),
            }
        ).encode(),
    )
    dlq = sqs.get_queue_url(QueueName="petstop-geocode-fixture-dlq.fifo")["QueueUrl"]
    message = sqs.send_message(
        QueueUrl=dlq,
        MessageBody=json.dumps(
            {"source": "vet", "run_id": failed_run, "batch_id": "batch-00000"}
        ),
        MessageGroupId="fixture",
        MessageDeduplicationId=str(uuid4()),
    )
    invoke("reconcile", {"source": "vet", "run_id": failed_run})
    wait_until(
        lambda: run_state(failed_run) == "failed", "dead-letter failure projection"
    )
    if not object_exists(f"work-failures/{message['MessageId']}.json"):
        raise RuntimeError("Dead-letter message was not durably archived")
    failure_queue = sqs.get_queue_url(
        QueueName="petstop-facility-invocation-failures-fixture"
    )["QueueUrl"]
    captured = sqs.send_message(
        QueueUrl=failure_queue,
        MessageBody=json.dumps(
            {
                "requestPayload": {"source": "vet", "run_id": failed_run},
                "responsePayload": {"errorType": "InjectedFailure"},
            }
        ),
    )
    wait_until(
        lambda: object_exists(f"invocation-failures/{captured['MessageId']}.json"),
        "async invocation failure capture",
    )
    print(
        "PASS: exact fixtures, token renewal, 429 recovery, malformed PDF preservation, duplicate load, database-outage replay, DLQ archive and invocation-failure capture.",
        flush=True,
    )


if __name__ == "__main__":
    main()
