from django.core.management.base import BaseCommand, CommandError

from facilities.ingestion.aws import client
from facilities.ingestion.status import identity, put_json, read_json


class Command(BaseCommand):
    help = "Approve a reviewed count-drop snapshot and re-emit its S3 notification."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=("vet", "pet_shop"), required=True)
        parser.add_argument("--run-id", required=True)
        parser.add_argument("--snapshot-sha256", required=True)

    def handle(self, *args, **options):
        import os

        source, run_id = identity(options["source"], options["run_id"])
        bucket = os.environ["FACILITY_SYNC_BUCKET"]
        s3 = client("s3")
        snapshot = read_json(s3, bucket, f"ready/{source}/{run_id}.json")
        if (
            not snapshot
            or snapshot.get("snapshot_sha256") != options["snapshot_sha256"]
        ):
            raise CommandError(
                "Snapshot is absent or its digest differs from the reviewed digest"
            )
        put_json(
            s3,
            bucket,
            f"approvals/{source}/{run_id}.json",
            {"snapshot_sha256": snapshot["snapshot_sha256"]},
        )
        put_json(s3, bucket, f"ready/{source}/{run_id}.json", snapshot)
        self.stdout.write("Approval stored; snapshot load requested.")
