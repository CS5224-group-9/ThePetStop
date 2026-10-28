import hashlib
import importlib.util
import io
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from botocore.exceptions import ClientError
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase

from facilities.ingestion import (
    dispatch,
    fetch,
    finalize,
    geocoding,
    loading,
    parsers,
    recovery,
    status,
)
from facilities.models import Facility, FacilitySyncEvent, FacilitySyncRun

spec = importlib.util.spec_from_file_location(
    "fixture_server",
    Path(__file__).resolve().parents[2] / "scripts/facilities/fixture_server.py",
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
ENV = {
    "FACILITY_SYNC_BUCKET": "test-bucket",
    "GEOCODE_QUEUE_URL": "http://localhost/queue.fifo",
    "ONEMAP_ACCESS_TOKEN": "test",
    "FACILITY_FIXTURE_MODE": "false",
}


class FakeS3:
    class Missing(Exception):
        pass

    exceptions = SimpleNamespace(NoSuchKey=Missing)

    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, **options):
        versions = self.objects.get(Key, [])
        etag = versions[-1]["ETag"] if versions else None
        if (
            options.get("IfNoneMatch") == "*"
            and versions
            or options.get("IfMatch")
            and options["IfMatch"] != etag
        ):
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        value = {
            "Body": Body,
            "ETag": hashlib.sha256(Body).hexdigest(),
            "VersionId": str(len(versions) + 1),
        }
        self.objects.setdefault(Key, []).append(value)
        return {k: v for k, v in value.items() if k != "Body"}

    def get_object(self, Bucket, Key, VersionId=None):
        try:
            obj = self.objects[Key][int(VersionId) - 1 if VersionId else -1]
        except KeyError:
            raise self.Missing from None
        return {**obj, "Body": io.BytesIO(obj["Body"])}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def get_paginator(self, name):
        return SimpleNamespace(
            paginate=lambda **kwargs: [
                {
                    "Contents": [
                        {"Key": key}
                        for key in sorted(self.objects)
                        if key.startswith(kwargs["Prefix"])
                    ]
                }
            ]
        )


class FakeSqs:
    def __init__(self):
        self.messages = []
        self.fail_at = None

    def send_message(self, **params):
        if self.fail_at == len(self.messages):
            raise RuntimeError("injected send failure")
        self.messages.append(params)


def snapshot(count=2):
    run_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    records = fetch.parse_registry_pdf(fixtures.pdf("vet"), "vet")[:count]
    for record in records:
        record.update(
            latitude=1.3,
            longitude=103.8,
            geocode_status="resolved",
            geocode_query=record["postal_code"],
            geocode_provider="onemap",
            geocoded_at=now,
        )
    value = {
        "schema_version": 1,
        "run_id": run_id,
        "source": "vet",
        "facility_type": "vet",
        "registry_url": fetch.DEFAULT_SOURCES["vet"],
        "document_url": "https://isomer-user-content.by.gov.sg/test.pdf",
        "document_sha256": "a" * 64,
        "raw_key": f"raw/vet/{'a' * 64}.pdf",
        "checked_at": now,
        "expected_record_count": len(records),
        "unlocated_count": 0,
        "records": records,
    }
    value["snapshot_sha256"] = status.digest(value)
    return value


@patch.dict(os.environ, ENV)
class IngestionUnitTests(SimpleTestCase):
    def test_pet_shop_approvals_are_read_from_the_pdf(self):
        rows = fetch.parse_registry_pdf(fixtures.pdf("pet_shop"), "pet_shop")
        self.assertEqual(
            [row["name"] for row in rows], ["FIXTURE SHOP A", "FIXTURE SHOP B"]
        )
        self.assertEqual(rows[0]["approved_animals"], ["dog", "cat"])
        self.assertEqual(
            rows[1]["approved_animals"],
            ["small_mammal", "bird", "marine_fish", "freshwater_fish"],
        )
        for invalid in ("yes", "**"):
            changed = [list(row) for row in fixtures.ROWS["pet_shop"]]
            changed[0][8] = invalid
            with (
                patch.dict(fixtures.ROWS, {"pet_shop": changed}),
                self.assertRaises(fetch.RegistryParseError),
            ):
                fetch.parse_registry_pdf(fixtures.pdf("pet_shop"), "pet_shop")

    def test_pet_shop_approval_headers_are_required_and_can_repeat(self):
        header = [""] * 8 + ["D", "C", "SM", "B", "MF", "F"]
        table = [
            header,
            fixtures.ROWS["pet_shop"][0],
            header,
            fixtures.ROWS["pet_shop"][1],
        ]

        def pdf(rows):
            return SimpleNamespace(
                pages=[
                    SimpleNamespace(
                        search=lambda pattern: [],
                        find_tables=lambda: [
                            SimpleNamespace(bbox=(0, 0, 100, 100), extract=lambda: rows)
                        ],
                    )
                ]
            )

        self.assertEqual(len(parsers._pet_shop_records(pdf(table))), 2)
        for rows in (
            table[1:],
            [header[:-1], fixtures.ROWS["pet_shop"][0]],
            [header, fixtures.ROWS["pet_shop"][0][:-1]],
        ):
            with self.assertRaises(fetch.RegistryParseError):
                parsers._pet_shop_records(pdf(rows))

    def test_revoked_pet_shop_table_is_excluded(self):
        header = [""] * 8 + ["D", "C", "SM", "B", "MF", "F"]
        active = SimpleNamespace(
            bbox=(0, 0, 100, 80), extract=lambda: [header, fixtures.ROWS["pet_shop"][0]]
        )
        revoked = SimpleNamespace(
            bbox=(0, 120, 100, 200), extract=lambda: [fixtures.ROWS["pet_shop"][1][:8]]
        )
        page = SimpleNamespace(
            search=lambda pattern: [{"top": 100}], find_tables=lambda: [active, revoked]
        )
        rows = parsers._pet_shop_records(SimpleNamespace(pages=[page]))
        self.assertEqual([row["source_key"] for row in rows], ["AB123456"])

    def test_failure_logs_exclude_unvalidated_batch_fields(self):
        with patch.object(status, "emit") as emit:
            status.fail(
                FakeS3(),
                "test-bucket",
                "vet",
                str(uuid4()),
                "geocoding",
                "invalid_message",
                batch_id={"unexpected": "untrusted payload"},
            )
        self.assertNotIn("batch_id", emit.call_args.kwargs["detail"])

    def test_invalid_queue_json_is_durably_quarantined_and_acknowledged(self):
        s3 = FakeS3()
        with patch.object(geocoding, "aws_client", return_value=s3):
            result = geocoding.handler(
                {"Records": [{"body": "not JSON", "messageId": "bad"}]}, None
            )
        self.assertEqual(result["results"], [{"status": "quarantined"}])
        self.assertIn("quarantine/bad.json", s3.objects)

    def test_registry_long_retry_after_is_deferred_without_sleeping(self):
        response = SimpleNamespace(status=429, getheader=lambda name: "120")
        connection = SimpleNamespace(
            request=lambda *args, **kwargs: None,
            getresponse=lambda: response,
            close=lambda: None,
        )
        with (
            patch.object(fetch, "HTTPSConnection", return_value=connection),
            patch.object(fetch.time, "sleep") as sleep,
        ):
            with self.assertRaises(fetch.RetryableRegistryFetchError) as error:
                fetch._open("https://avs.nparks.gov.sg/test", fetch.ALLOWED_HOSTS)
        self.assertEqual(error.exception.retry_after, 120)
        sleep.assert_not_called()

    def test_concurrent_fetch_lease_rejects_second_writer(self):
        s3 = FakeS3()
        run_id = str(uuid4())
        event = {"source": "vet", "run_id": run_id}
        status.put_json(
            s3,
            "test-bucket",
            f"leases/vet/{run_id}.json",
            {"expires_at": datetime.now(UTC).timestamp() + 60},
        )
        with patch("facilities.ingestion.aws.client", return_value=s3):
            with self.assertRaisesRegex(RuntimeError, "already being fetched"):
                status.serialized(lambda event, context: None)(event, None)

    def test_reviewed_pdf_fixtures_preserve_postal_codes(self):
        for source in ("vet", "pet_shop"):
            rows = fetch.parse_registry_pdf(fixtures.pdf(source), source)
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["postal_code"].startswith("0") for row in rows))
        with self.assertRaises(fetch.RegistryParseError):
            fetch.parse_registry_pdf(b"%PDF-invalid", "vet")

    def test_url_spaces_are_encoded_without_double_encoding(self):
        url = "https://isomer-user-content.by.gov.sg/a file%20name.pdf"
        self.assertEqual(
            fetch._validate_url(url, fetch.ALLOWED_HOSTS),
            url.replace("a file", "a%20file"),
        )

    def test_partial_dispatch_resumes_without_losing_unsent_work(self):
        s3, sqs = FakeS3(), FakeSqs()
        run_id = str(uuid4())
        rows = fetch.parse_registry_pdf(fixtures.pdf("vet"), "vet")
        batches, keys, versions = dispatch.create_batch_artifacts(
            s3, "test-bucket", "vet", run_id, rows, 1
        )
        params = (
            s3,
            sqs,
            ENV["GEOCODE_QUEUE_URL"],
            "test-bucket",
            "vet",
            run_id,
            "parsed.json",
            "a" * 64,
            batches,
            keys,
            versions,
        )
        sqs.fail_at = 1
        with self.assertRaises(RuntimeError):
            dispatch.dispatch_batches(*params)
        sqs.fail_at = None
        dispatch.resume_dispatch(
            s3, sqs, ENV["GEOCODE_QUEUE_URL"], "test-bucket", "vet", run_id
        )
        self.assertEqual(len(sqs.messages), 2)
        self.assertEqual(
            len({row["MessageDeduplicationId"] for row in sqs.messages}), 2
        )

    def test_throttle_cooldown_survives_invocations(self):
        s3 = FakeS3()
        geocoding._defer_after_throttle(
            s3, "test-bucket", geocoding._UpstreamError(429, "120"), 1
        )
        with self.assertRaises(geocoding.RetryableGeocodeError):
            geocoding._reserve_request(
                s3,
                "test-bucket",
                SimpleNamespace(get_remaining_time_in_millis=lambda: 1000),
            )
        self.assertGreater(
            status.read_json(s3, "test-bucket", geocoding.RATE_STATE_KEY)[
                "cooldown_until"
            ],
            datetime.now(UTC).timestamp(),
        )

    def test_stale_geocode_cache_is_refreshed(self):
        s3 = FakeS3()
        postal = "080001"
        query = {
            "query_id": hashlib.sha256(postal.encode()).hexdigest(),
            "postal_code": postal,
            "address": "Fixture",
            "source": "vet",
            "run_id": str(uuid4()),
        }
        status.put_json(
            s3,
            "test-bucket",
            f"cache/geocoding/{query['query_id']}.json",
            {
                **query,
                "schema_version": 1,
                "status": "resolved",
                "latitude": 1.3,
                "longitude": 103.8,
                "geocoded_at": (datetime.now(UTC) - timedelta(days=91)).isoformat(),
            },
        )
        with patch.object(
            geocoding,
            "_search",
            return_value=[{"POSTAL": postal, "LATITUDE": 1.31, "LONGITUDE": 103.81}],
        ) as search:
            value = geocoding._result_for_query(s3, "test-bucket", query, None, 1)
        search.assert_called_once()
        self.assertEqual(value["latitude"], 1.31)


@patch.dict(os.environ, ENV)
class IngestionDatabaseTests(TestCase):
    def test_approval_updates_and_older_snapshots_preserve_enriched_data(self):
        def pet_snapshot(animals):
            value = snapshot()
            value.update(
                source="pet_shop",
                facility_type="pet_shop",
                registry_url=fetch.DEFAULT_SOURCES["pet_shop"],
                parser_version="2",
                raw_key=f"raw/pet_shop/{'a' * 64}.pdf",
            )
            for record in value["records"]:
                record.update(
                    source_id="pet_shop",
                    facility_type="pet_shop",
                    approved_animals=animals,
                )
            value["snapshot_sha256"] = status.digest(
                {key: item for key, item in value.items() if key != "snapshot_sha256"}
            )
            return value

        first = pet_snapshot(["cat"])
        loading.load_snapshot(first)
        changed = pet_snapshot(["dog", "cat"])
        result = loading.load_snapshot(changed)
        self.assertEqual(result["updated"], 2)
        self.assertEqual(Facility.objects.first().approved_animals, ["dog", "cat"])
        older_format = pet_snapshot(["cat"])
        older_format["parser_version"] = "1"
        for record in older_format["records"]:
            record.pop("approved_animals")
        older_format["snapshot_sha256"] = status.digest(
            {
                key: item
                for key, item in older_format.items()
                if key != "snapshot_sha256"
            }
        )
        loading.load_snapshot(older_format)
        self.assertEqual(Facility.objects.first().approved_animals, ["dog", "cat"])
        for invalid in (["dragon"], ["cat", "cat"], "cat", [["cat"]], [], None):
            with (
                self.subTest(invalid=invalid),
                self.assertRaises(loading.SnapshotValidationError),
            ):
                loading.load_snapshot(pet_snapshot(invalid))

    def test_invalid_status_is_quarantined_without_creating_a_run(self):
        s3 = FakeS3()
        run_id, event_id = str(uuid4()), str(uuid4())
        key = f"status/vet/{run_id}/{event_id}.json"
        status.put_json(
            s3,
            "test-bucket",
            key,
            {
                "schema_version": 1,
                "source": "vet",
                "run_id": run_id,
                "event_id": event_id,
            },
        )
        event = {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "s3": {"bucket": {"name": "test-bucket"}, "object": {"key": key}},
                }
            ]
        }
        loading.load_s3_event(event, s3)
        self.assertFalse(FacilitySyncRun.objects.exists())
        self.assertIn(f"quarantine/{key}", s3.objects)
        self.assertIn(f"projected/vet/{run_id}/{event_id}.json", s3.objects)

    def test_duplicate_load_and_out_of_order_snapshot(self):
        value = snapshot()
        loading.load_snapshot(value)
        self.assertTrue(loading.load_snapshot(value)["idempotent"])
        older = snapshot()
        older["checked_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        older.pop("snapshot_sha256")
        older["snapshot_sha256"] = status.digest(older)
        self.assertEqual(loading.load_snapshot(older)["status"], "superseded")
        self.assertEqual(Facility.objects.count(), 2)

    def test_count_drop_preserves_last_good_dataset_until_approved(self):
        loading.load_snapshot(snapshot())
        value = snapshot(1)
        with self.assertRaises(loading.SnapshotReviewRequired):
            loading.load_snapshot(value)
        self.assertEqual(Facility.objects.filter(active=True).count(), 2)
        self.assertEqual(
            FacilitySyncRun.objects.get(pk=value["run_id"]).status, "review_required"
        )
        loading.load_snapshot(value, approve_drop=True)
        self.assertEqual(Facility.objects.filter(active=True).count(), 1)

    def test_database_write_failure_rolls_back_entire_snapshot(self):
        value = snapshot()
        original = Facility.save
        calls = 0

        def broken_save(instance, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected crash")
            return original(instance, *args, **kwargs)

        with (
            patch.object(Facility, "save", broken_save),
            self.assertRaises(RuntimeError),
        ):
            loading.load_snapshot(value)
        self.assertFalse(Facility.objects.exists())
        self.assertEqual(
            FacilitySyncRun.objects.get(pk=value["run_id"]).status, "failed"
        )

    def test_failure_recording_does_not_mask_original_error(self):
        with (
            patch.object(
                loading, "_apply_snapshot", side_effect=RuntimeError("original")
            ),
            patch.object(
                loading, "_record_failure", side_effect=OperationalError("offline")
            ),
            self.assertRaisesRegex(RuntimeError, "original"),
        ):
            loading.load_snapshot(snapshot())

    def test_status_projection_is_idempotent_and_does_not_regress_success(self):
        value = snapshot()
        loading.load_snapshot(value)
        s3 = FakeS3()
        event = status.emit(
            s3,
            "test-bucket",
            "vet",
            value["run_id"],
            "geocoding",
            "batch_completed",
            detail={"batch_id": "batch-00000"},
        )
        status.project(event)
        status.project(event)
        status.project(
            status.emit(
                s3,
                "test-bucket",
                "vet",
                value["run_id"],
                "queued",
                "dispatched",
                detail={"batch_count": 1},
            )
        )
        run = FacilitySyncRun.objects.get(pk=value["run_id"])
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.stage, "complete")
        self.assertEqual(run.completed_batch_count, 1)
        self.assertEqual(run.expected_batch_count, 1)
        self.assertEqual(
            FacilitySyncEvent.objects.filter(event_id=event["event_id"]).count(), 1
        )

    def test_vertical_slice_duplicate_worker_and_lost_notification_recovery(self):
        s3, sqs = FakeS3(), FakeSqs()
        run_id = str(uuid4())
        pdf = fixtures.pdf("vet")
        with (
            patch.object(fetch, "aws_client", return_value=s3),
            patch.object(
                fetch,
                "_open",
                side_effect=[
                    (
                        fetch.DEFAULT_SOURCES["vet"],
                        b'<a href="https://isomer-user-content.by.gov.sg/vet.pdf">vet</a>',
                    ),
                    ("https://isomer-user-content.by.gov.sg/vet.pdf", pdf),
                ],
            ),
        ):
            status.begin(s3, "test-bucket", "vet", run_id)
            fetch.fetch_registry("vet", run_id, s3, sqs)
        message = json.loads(sqs.messages[0]["MessageBody"])
        calls = []

        def search(postal, callback):
            calls.append(postal)
            if len(calls) == 2:
                raise geocoding.RetryableGeocodeError("injected interruption")
            return [{"POSTAL": postal, "LATITUDE": 1.3, "LONGITUDE": 103.8}]

        with patch.object(geocoding, "_search", side_effect=search):
            with self.assertRaises(geocoding.RetryableGeocodeError):
                geocoding.process_batch(message, s3)
            self.assertNotIn(f"ready/vet/{run_id}.json", s3.objects)
            geocoding.process_batch(message, s3)
            geocoding.process_batch(message, s3)
        self.assertEqual(len(calls), 3)
        key = f"ready/vet/{run_id}.json"
        s3.delete_object(Bucket="test-bucket", Key=key)

        def competing_finalizer(s3_client, bucket, artifact_key, value):
            status.put_json(s3_client, bucket, artifact_key, value)
            return False

        with patch.object(finalize, "create_json", side_effect=competing_finalizer):
            self.assertEqual(
                finalize.finalize_if_complete(
                    s3, "test-bucket", "vet", run_id, message["manifest_key"]
                ),
                key,
            )
        result = recovery.repair_run(s3, sqs, "test-bucket", "vet", run_id, force=True)
        self.assertEqual(result, "load_replayed")
        key = f"ready/vet/{run_id}.json"
        event = {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "s3": {"bucket": {"name": "test-bucket"}, "object": {"key": key}},
                }
            ]
        }
        loading.load_s3_event(event, s3)
        loading.load_s3_event(event, s3)
        self.assertEqual(Facility.objects.count(), 2)
        self.assertEqual(FacilitySyncRun.objects.get(pk=run_id).status, "succeeded")
        self.assertIsNotNone(
            status.read_json(s3, "test-bucket", f"loaded/vet/{run_id}.json")
        )
