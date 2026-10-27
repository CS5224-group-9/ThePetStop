import os

import boto3
from botocore.config import Config


def client(service):
    options = {
        "region_name": os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1"),
        "config": Config(s3={"addressing_style": "path"}),
    }
    if endpoint := os.environ.get("AWS_ENDPOINT_URL"):
        options["endpoint_url"] = endpoint
    return boto3.client(service, **options)
