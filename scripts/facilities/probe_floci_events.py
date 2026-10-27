"""Exercise local SQS→Lambda and S3→Lambda delivery through Floci."""

import io
import json
import sys
import time
import uuid
import zipfile
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ENDPOINT = "http://localhost:4566"
REGION = "ap-southeast-1"
ACCOUNT_ID = "000000000000"
FUNCTION = "petstop-floci-event-probe"
ROLE = "petstop-floci-event-probe"
QUEUE = "petstop-floci-event-probe.fifo"
BUCKET = "petstop-floci-event-probe"

HANDLER = '''import json
import os
import socket
from urllib.parse import unquote_plus

import boto3
from botocore.config import Config

def handler(event, context):
    s3 = boto3.client("s3", config=Config(s3={"addressing_style": "path"}))
    receipts = []
    for record in event.get("Records", []):
        source = record.get("eventSource")
        if source == "aws:sqs":
            message = json.loads(record["body"])
            kind, run_id = "sqs", message["run_id"]
        elif source == "aws:s3":
            key = unquote_plus(record["s3"]["object"]["key"])
            kind, run_id = "s3", key.rsplit("/", 1)[-1].removesuffix(".json")
        else:
            continue

        checks = {}
        for name, host, port in (("floci", "floci", 4566), ("postgres", "db", 5432)):
            try:
                with socket.create_connection((host, port), timeout=3):
                    checks[name] = True
            except OSError:
                checks[name] = False

        receipt = {"source": source, "checks": checks}
        s3.put_object(
            Bucket=os.environ["PROBE_BUCKET"],
            Key=f"receipts/{run_id}/{kind}.json",
            Body=json.dumps(receipt).encode(),
            ContentType="application/json",
        )
        receipts.append(receipt)
    return {"receipts": receipts}
'''


def wait_for_function(lambdas):
    for _ in range(60):
        config = lambdas.get_function_configuration(FunctionName=FUNCTION)
        if config.get("State") in (None, "Active") and config.get(
            "LastUpdateStatus"
        ) in (None, "Successful"):
            return
        if (
            config.get("State") == "Failed"
            or config.get("LastUpdateStatus") == "Failed"
        ):
            raise RuntimeError(f"Floci Lambda is not ready: {config}")
        time.sleep(1)
    raise TimeoutError("Timed out waiting for the event probe Lambda")


def provision(session):
    iam = session.client("iam", endpoint_url=ENDPOINT)
    lambdas = session.client("lambda", endpoint_url=ENDPOINT)
    sqs = session.client("sqs", endpoint_url=ENDPOINT)
    s3 = session.client(
        "s3",
        endpoint_url=ENDPOINT,
        config=Config(s3={"addressing_style": "path"}),
    )

    queue = sqs.create_queue(
        QueueName=QUEUE,
        Attributes={"FifoQueue": "true", "ContentBasedDeduplication": "true"},
    )["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue,
        AttributeNames=["QueueArn"],
    )["Attributes"]["QueueArn"]

    try:
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
    except ClientError as error:
        if error.response["Error"]["Code"] not in (
            "BucketAlreadyExists",
            "BucketAlreadyOwnedByYou",
        ):
            raise

    bucket_arn = f"arn:aws:s3:::{BUCKET}"
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE}"
    try:
        iam.create_role(
            RoleName=ROLE,
            AssumeRolePolicyDocument=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "lambda.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                }
            ),
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "EntityAlreadyExists":
            raise

    iam.put_role_policy(
        RoleName=ROLE,
        PolicyName="petstop-floci-event-probe",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "sqs:ReceiveMessage",
                            "sqs:DeleteMessage",
                            "sqs:GetQueueAttributes",
                            "sqs:ChangeMessageVisibility",
                        ],
                        "Resource": queue_arn,
                    },
                    {
                        "Effect": "Allow",
                        "Action": "s3:PutObject",
                        "Resource": f"{bucket_arn}/receipts/*",
                    },
                ],
            }
        ),
    )

    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("probe.py", HANDLER)
    function_code = {
        "Runtime": "python3.13",
        "Role": role_arn,
        "Handler": "probe.handler",
        "Code": {"ZipFile": bundle.getvalue()},
        "Timeout": 15,
        "MemorySize": 128,
        "Environment": {"Variables": {"PROBE_BUCKET": BUCKET}},
    }

    try:
        lambdas.create_function(FunctionName=FUNCTION, **function_code)
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceConflictException":
            raise
        lambdas.update_function_configuration(
            FunctionName=FUNCTION,
            Runtime="python3.13",
            Role=role_arn,
            Handler="probe.handler",
            Timeout=15,
            MemorySize=128,
            Environment={"Variables": {"PROBE_BUCKET": BUCKET}},
        )
        wait_for_function(lambdas)
        lambdas.update_function_code(FunctionName=FUNCTION, ZipFile=bundle.getvalue())

    wait_for_function(lambdas)
    function_arn = lambdas.get_function(FunctionName=FUNCTION)["Configuration"][
        "FunctionArn"
    ]

    mappings = lambdas.list_event_source_mappings(
        FunctionName=FUNCTION,
        EventSourceArn=queue_arn,
    )["EventSourceMappings"]
    if not mappings:
        lambdas.create_event_source_mapping(
            FunctionName=FUNCTION,
            EventSourceArn=queue_arn,
            BatchSize=1,
            Enabled=True,
        )
    else:
        if mappings[0].get("State") != "Enabled":
            lambdas.update_event_source_mapping(
                UUID=mappings[0]["UUID"],
                Enabled=True,
            )

    for _ in range(30):
        mappings = lambdas.list_event_source_mappings(
            FunctionName=FUNCTION,
            EventSourceArn=queue_arn,
        )["EventSourceMappings"]
        if mappings and mappings[0].get("State") == "Enabled":
            break
        if mappings and mappings[0].get("State") == "Disabled":
            raise RuntimeError("Floci did not enable the SQS event source mapping")
        time.sleep(1)
    else:
        raise TimeoutError("Timed out waiting for the SQS event source mapping")

    try:
        lambdas.add_permission(
            FunctionName=FUNCTION,
            StatementId="petstop-floci-event-probe-s3",
            Action="lambda:InvokeFunction",
            Principal="s3.amazonaws.com",
            SourceArn=bucket_arn,
        )
    except ClientError as error:
        if error.response["Error"]["Code"] not in (
            "ResourceConflictException",
            "StatementIdAlreadyExists",
        ):
            raise

    s3.put_bucket_notification_configuration(
        Bucket=BUCKET,
        NotificationConfiguration={
            "LambdaFunctionConfigurations": [
                {
                    "Id": "ready-prefix-event-probe",
                    "LambdaFunctionArn": function_arn,
                    "Events": ["s3:ObjectCreated:*"],
                    "Filter": {
                        "Key": {
                            "FilterRules": [
                                {"Name": "prefix", "Value": "ready/"}
                            ]
                        }
                    },
                }
            ]
        },
    )
    return sqs, s3, queue


def main():
    parsed = urlparse(ENDPOINT)
    if parsed.scheme != "http" or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("The event probe only permits a local Floci endpoint")

    session = boto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name=REGION,
    )
    sqs, s3, queue = provision(session)
    run_id = uuid.uuid4().hex
    sqs.send_message(
        QueueUrl=queue,
        MessageBody=json.dumps({"run_id": run_id}),
        MessageGroupId="probe",
    )
    s3.put_object(
        Bucket=BUCKET,
        Key=f"ready/{run_id}.json",
        Body=json.dumps({"run_id": run_id}),
        ContentType="application/json",
    )

    expected = {f"receipts/{run_id}/sqs.json", f"receipts/{run_id}/s3.json"}
    found = set()
    for _ in range(60):
        response = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"receipts/{run_id}/")
        found.update(item["Key"] for item in response.get("Contents", []))
        if expected <= found:
            break
        time.sleep(1)

    results = {}
    for key in sorted(found & expected):
        results[key.rsplit("/", 1)[-1].removesuffix(".json")] = json.loads(
            s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        )
    print(json.dumps(results, indent=2))
    if set(results) != {"sqs", "s3"} or any(
        not all(receipt["checks"].values()) for receipt in results.values()
    ):
        raise TimeoutError(
            "Did not receive both healthy event receipts. Check Floci logs, "
            "the Lambda event mapping, and the S3 notification configuration."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Floci event probe failed: {error}", file=sys.stderr)
        raise
