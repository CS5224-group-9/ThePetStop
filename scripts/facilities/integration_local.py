"""Run the live AVS-to-PostgreSQL path through local Floci events."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import boto3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / ".env")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from facilities.models import Facility, FacilitySyncRun


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint-url", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--source", choices=("vet", "pet_shop", "both"), default="both")
    args = parser.parse_args()
    if args.endpoint_url != "http://localhost:4566":
        raise ValueError("The integration runner only permits local Floci")
    session = boto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="ap-southeast-1",
    )
    lambdas = session.client("lambda", endpoint_url=args.endpoint_url)
    sources = ("vet", "pet_shop") if args.source == "both" else (args.source,)
    runs = {}
    for source in sources:
        result = lambdas.invoke(
            FunctionName="petstop-facility-fetch-local",
            InvocationType="RequestResponse",
            Payload=json.dumps({"operation": "start", "source": source}).encode(),
        )
        payload = json.loads(result["Payload"].read() or b"{}")
        if result.get("FunctionError"):
            raise RuntimeError(f"{source} fetch failed: {payload}")
        run_id = payload.get("run_id")
        if not run_id:
            raise RuntimeError(f"{source} fetch did not return a run ID: {payload}")
        runs[source] = run_id

    deadline = time.monotonic() + args.timeout_seconds
    while time.monotonic() < deadline:
        rows = {
            source: FacilitySyncRun.objects.filter(run_id=run_id).first()
            for source, run_id in runs.items()
        }
        failed = [row for row in rows.values() if row and row.status == "failed"]
        if failed:
            details = [
                {
                    "run_id": str(row.run_id),
                    "source": row.source,
                    "error_code": row.error_code,
                }
                for row in failed
            ]
            raise RuntimeError(f"Ingestion failed: {details}")
        if all(
            row and row.status in {"succeeded", "superseded"} for row in rows.values()
        ):
            break
        time.sleep(3)
    else:
        pending = {
            source: {
                "run_id": run_id,
                "status": (rows[source].status if rows[source] else "not loaded"),
            }
            for source, run_id in runs.items()
        }
        raise TimeoutError(f"Timed out waiting for facility loads: {pending}")

    report = []
    for source, run_id in runs.items():
        run = FacilitySyncRun.objects.get(run_id=run_id)
        count = Facility.objects.filter(source_id=source, active=True).count()
        if run.status == "succeeded" and count == 0:
            raise RuntimeError(f"{source} succeeded but has no active facilities")
        report.append(
            {
                "source": source,
                "run_id": str(run_id),
                "status": run.status,
                "parsed": run.parsed_count,
                "inserted": run.inserted_count,
                "updated": run.updated_count,
                "unchanged": run.unchanged_count,
                "unlocated": run.unlocated_count,
                "active_facilities": count,
            }
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Local facility integration failed: {error}", file=sys.stderr)
        raise
