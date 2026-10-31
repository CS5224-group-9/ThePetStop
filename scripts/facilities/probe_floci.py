"""Create and invoke a local Lambda that checks Floci/PostgreSQL networking."""

import json
import sys
import time
import zipfile
from io import BytesIO
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

ENDPOINT = "http://localhost:4566"
FUNCTION_NAME = "petstop-floci-network-probe"
ROLE_NAME = "petstop-floci-network-probe"
ACCOUNT_ID = "000000000000"

HANDLER = '''import socket

def handler(event, context):
    checks = {}
    for name, host, port in (("floci", "floci", 4566), ("postgres", "db", 5432)):
        try:
            with socket.create_connection((host, port), timeout=3):
                checks[name] = {"reachable": True}
        except OSError as error:
            checks[name] = {"reachable": False, "error": type(error).__name__}
    return {"checks": checks}
'''


def wait_for_function(lambdas):
    for _ in range(30):
        config = lambdas.get_function_configuration(FunctionName=FUNCTION_NAME)
        state = config.get("State")
        update = config.get("LastUpdateStatus")
        if state in (None, "Active") and update in (None, "Successful"):
            return
        if state == "Failed" or update == "Failed":
            raise RuntimeError(f"Floci Lambda is not ready: {config}")
        time.sleep(1)
    raise TimeoutError("Timed out waiting for the Floci probe Lambda")


def main():
    parsed = urlparse(ENDPOINT)
    if parsed.scheme != "http" or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("The probe only permits a local Floci endpoint")

    session = boto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="ap-southeast-1",
    )
    iam = session.client("iam", endpoint_url=ENDPOINT)
    lambdas = session.client("lambda", endpoint_url=ENDPOINT)
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"
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

    try:
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust),
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "EntityAlreadyExists":
            raise

    bundle = BytesIO()
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("probe.py", HANDLER)

    try:
        lambdas.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime="python3.13",
            Role=role_arn,
            Handler="probe.handler",
            Code={"ZipFile": bundle.getvalue()},
            Timeout=10,
            MemorySize=128,
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceConflictException":
            raise
        lambdas.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Runtime="python3.13",
            Role=role_arn,
            Handler="probe.handler",
            Timeout=10,
            MemorySize=128,
        )
        wait_for_function(lambdas)
        lambdas.update_function_code(
            FunctionName=FUNCTION_NAME,
            ZipFile=bundle.getvalue(),
        )

    wait_for_function(lambdas)
    result = lambdas.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=b"{}",
    )
    payload = json.loads(result["Payload"].read())
    print(json.dumps(payload, indent=2))

    checks = payload.get("checks", {})
    if result.get("FunctionError") or not all(
        checks.get(name, {}).get("reachable") for name in ("floci", "postgres")
    ):
        raise RuntimeError("Probe failed; check the Compose network and Floci logs")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Floci probe failed: {error}", file=sys.stderr)
        raise
