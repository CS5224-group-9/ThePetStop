import os

import boto3
from botocore.config import Config


def _close_emulator_connection(request, **kwargs):
    request.headers["Connection"] = "close"


def client(service):
    options = {
        "region_name": os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1"),
        "config": Config(
            connect_timeout=3,
            read_timeout=15,
            retries={"mode": "standard", "max_attempts": 3},
            s3={"addressing_style": "path"},
        ),
    }
    if endpoint := os.environ.get("AWS_ENDPOINT_URL"):
        options["endpoint_url"] = endpoint
    result = boto3.client(service, **options)
    if endpoint and service == "s3":
        # Floci can leave a reused connection invalid after rejecting a conditional PUT.
        result.meta.events.register("before-sign.s3", _close_emulator_connection)
    return result
