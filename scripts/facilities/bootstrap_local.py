"""Provision the facility ingestion resources in a local Floci instance."""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import dotenv_values

ACCOUNT_ID = "000000000000"
BUCKET = "petstop-facility-sync-local"
QUEUE = "petstop-geocode-local.fifo"
DLQ = "petstop-geocode-local-dlq.fifo"
ROLE = "petstop-facility-ingestion-local"
FUNCTIONS = {
    "fetch": ("petstop-facility-fetch-local", "facilities.ingestion.handlers.fetch"),
    "geocode": (
        "petstop-facility-geocode-local",
        "facilities.ingestion.handlers.geocode",
    ),
    "load": ("petstop-facility-load-local", "facilities.ingestion.handlers.load"),
}
ROOT = Path(__file__).resolve().parents[2]


def _local_endpoint(value):
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("Only an HTTP localhost Floci endpoint is allowed")
    return value.rstrip("/")


def _ignore_existing(call, *codes):
    try:
        return call()
    except ClientError as error:
        if error.response["Error"]["Code"] not in codes:
            raise
        return None


def _wait_function(lambdas, name):
    for _ in range(60):
        config = lambdas.get_function_configuration(FunctionName=name)
        if config.get("State") in (None, "Active") and config.get(
            "LastUpdateStatus"
        ) in (None, "Successful"):
            return
        if (
            config.get("State") == "Failed"
            or config.get("LastUpdateStatus") == "Failed"
        ):
            raise RuntimeError(f"Floci function {name} failed to update")
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint-url", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    endpoint = _local_endpoint(args.endpoint_url)
    if not args.image:
        raise ValueError("--image is required")

    session = boto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="ap-southeast-1",
    )
    config = Config(
        connect_timeout=3,
        read_timeout=10,
        retries={"max_attempts": 1},
        s3={"addressing_style": "path"},
    )
    iam = session.client("iam", endpoint_url=endpoint, config=config)
    s3 = session.client("s3", endpoint_url=endpoint, config=config)
    sqs = session.client("sqs", endpoint_url=endpoint, config=config)
    lambdas = session.client("lambda", endpoint_url=endpoint, config=config)

    dead_letter_url = sqs.create_queue(
        QueueName=DLQ,
        Attributes={"FifoQueue": "true", "ContentBasedDeduplication": "true"},
    )["QueueUrl"]
    dead_letter_arn = sqs.get_queue_attributes(
        QueueUrl=dead_letter_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]
    queue_url = sqs.create_queue(
        QueueName=QUEUE,
        Attributes={
            "FifoQueue": "true",
            "ContentBasedDeduplication": "true",
            "VisibilityTimeout": "900",
            "RedrivePolicy": json.dumps(
                {"deadLetterTargetArn": dead_letter_arn, "maxReceiveCount": "5"}
            ),
        },
    )["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]
    queue_url = queue_url.replace("localhost:4566", "floci:4566").replace(
        "127.0.0.1:4566", "floci:4566"
    )
    _ignore_existing(
        lambda: s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-southeast-1"},
        ),
        "BucketAlreadyExists",
        "BucketAlreadyOwnedByYou",
    )
    s3.put_bucket_versioning(
        Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"}
    )

    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    _ignore_existing(
        lambda: iam.create_role(
            RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust)
        ),
        "EntityAlreadyExists",
    )
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE}"
    iam.put_role_policy(
        RoleName=ROLE,
        PolicyName="facility-ingestion-local",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "s3:ListBucket",
                        "Resource": f"arn:aws:s3:::{BUCKET}",
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:PutObject"],
                        "Resource": f"arn:aws:s3:::{BUCKET}/*",
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "sqs:SendMessage",
                            "sqs:ReceiveMessage",
                            "sqs:DeleteMessage",
                            "sqs:GetQueueAttributes",
                            "sqs:ChangeMessageVisibility",
                        ],
                        "Resource": queue_arn,
                    },
                ],
            }
        ),
    )

    local_env = dotenv_values(ROOT / "backend" / ".env")
    if not (
        local_env.get("ONEMAP_ACCESS_TOKEN")
        or (local_env.get("ONEMAP_EMAIL") and local_env.get("ONEMAP_PASSWORD"))
    ):
        raise ValueError("Set OneMap token or account credentials in backend/.env")
    common = {
        "AWS_ENDPOINT_URL": "http://floci:4566",
        "AWS_ACCESS_KEY_ID": "test",
        "AWS_SECRET_ACCESS_KEY": "test",
        "AWS_DEFAULT_REGION": "ap-southeast-1",
        "FACILITY_SYNC_BUCKET": BUCKET,
        "FACILITY_FIXTURE_MODE": "false",
    }
    db_env = {
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DJANGO_SECRET_KEY": "local-floci-only-secret",
        "DATABASE_URL": "postgresql://petstop:petstop@db:5432/petstop",
        "DJANGO_DEBUG": "false",
    }
    geocode_env = {
        key: str(local_env[key])
        for key in ("ONEMAP_ACCESS_TOKEN", "ONEMAP_EMAIL", "ONEMAP_PASSWORD")
        if local_env.get(key)
    }
    environments = {
        "fetch": {**common, "GEOCODE_QUEUE_URL": queue_url},
        "geocode": {
            **common,
            "GEOCODE_QUEUE_URL": queue_url,
            "ONEMAP_REQUESTS_PER_MINUTE": str(
                local_env.get("ONEMAP_REQUESTS_PER_MINUTE", "75")
            ),
            **geocode_env,
        },
        "load": {**common, **db_env},
    }

    for stage, (name, handler) in FUNCTIONS.items():
        function_args = {
            "PackageType": "Image",
            "Role": role_arn,
            "Code": {"ImageUri": args.image},
            "ImageConfig": {"Command": [handler]},
            "Timeout": 120 if stage == "geocode" else 60,
            "MemorySize": 1024,
            "Environment": {"Variables": environments[stage]},
        }
        try:
            lambdas.create_function(FunctionName=name, **function_args)
        except ClientError as error:
            if error.response["Error"]["Code"] != "ResourceConflictException":
                raise
            lambdas.update_function_configuration(
                FunctionName=name,
                Role=role_arn,
                ImageConfig={"Command": [handler]},
                Timeout=function_args["Timeout"],
                MemorySize=function_args["MemorySize"],
                Environment=function_args["Environment"],
            )
            _wait_function(lambdas, name)
            lambdas.update_function_code(FunctionName=name, ImageUri=args.image)
        _wait_function(lambdas, name)

    mappings = lambdas.list_event_source_mappings(
        FunctionName=FUNCTIONS["geocode"][0], EventSourceArn=queue_arn
    )["EventSourceMappings"]
    if not mappings:
        mapping = lambdas.create_event_source_mapping(
            FunctionName=FUNCTIONS["geocode"][0],
            EventSourceArn=queue_arn,
            BatchSize=1,
            Enabled=True,
        )
        mapping_id = mapping["UUID"]
    elif mappings[0].get("State") != "Enabled":
        mapping = lambdas.update_event_source_mapping(
            UUID=mappings[0]["UUID"], Enabled=True
        )
        mapping_id = mapping["UUID"]
    else:
        mapping_id = mappings[0]["UUID"]
    for _ in range(60):
        state = lambdas.get_event_source_mapping(UUID=mapping_id).get("State")
        if state == "Enabled":
            break
        if state in {"Disabled", "Failed"}:
            raise RuntimeError(f"Floci could not enable the SQS mapping ({state})")
        time.sleep(1)
    else:
        raise TimeoutError("Timed out waiting for the geocoding SQS mapping")

    load_arn = lambdas.get_function(FunctionName=FUNCTIONS["load"][0])["Configuration"][
        "FunctionArn"
    ]
    _ignore_existing(
        lambda: lambdas.add_permission(
            FunctionName=FUNCTIONS["load"][0],
            StatementId="facility-sync-s3-local",
            Action="lambda:InvokeFunction",
            Principal="s3.amazonaws.com",
            SourceArn=f"arn:aws:s3:::{BUCKET}",
        ),
        "ResourceConflictException",
        "StatementIdAlreadyExists",
    )
    s3.put_bucket_notification_configuration(
        Bucket=BUCKET,
        NotificationConfiguration={
            "LambdaFunctionConfigurations": [
                {
                    "Id": "facility-ready-local",
                    "LambdaFunctionArn": load_arn,
                    "Events": ["s3:ObjectCreated:*"],
                    "Filter": {
                        "Key": {"FilterRules": [{"Name": "prefix", "Value": "ready/"}]}
                    },
                }
            ]
        },
    )
    print(
        json.dumps(
            {
                "endpoint": endpoint,
                "bucket": BUCKET,
                "queue": QUEUE,
                "functions": [v[0] for v in FUNCTIONS.values()],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Local facility bootstrap failed: {error}", file=sys.stderr)
        raise
