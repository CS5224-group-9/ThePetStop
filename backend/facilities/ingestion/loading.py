import json
import logging
import os
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote_plus, urlparse
from uuid import UUID, uuid5

from django.db import transaction
from django.utils import timezone as django_timezone
from django.utils.dateparse import parse_date, parse_datetime

from facilities.animals import ANIMAL_COLUMNS
from facilities.ingestion import status as run_status
from facilities.ingestion.aws import client as aws_client
from facilities.models import (
    Facility,
    FacilitySource,
    FacilitySourceState,
    FacilitySyncEvent,
    FacilitySyncRun,
)

OFFICIAL_HOSTS = {"avs.nparks.gov.sg", "isomer-user-content.by.gov.sg"}
SINGAPORE_BOUNDS = (
    Decimal("1.15"),
    Decimal("1.5"),
    Decimal("103.55"),
    Decimal("104.15"),
)


class SnapshotValidationError(ValueError):
    pass


class SnapshotReviewRequired(SnapshotValidationError):
    pass


def _digest(snapshot):
    content = dict(snapshot)
    supplied = content.pop("snapshot_sha256", None)
    actual = run_status.digest(content)
    if not isinstance(supplied, str) or supplied != actual:
        raise SnapshotValidationError("Snapshot digest is invalid")


def _checked_url(value, fixture_mode):
    if not isinstance(value, str) or len(value) > 1000:
        raise SnapshotValidationError("Snapshot contains an invalid source URL")
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise SnapshotValidationError(
            "Snapshot source URL has an invalid port"
        ) from error
    schemes = {"https"}
    if fixture_mode:
        schemes.add("http")
    hosts = OFFICIAL_HOSTS
    if fixture_mode:
        config = json.loads(os.environ.get("FACILITY_SOURCE_CONFIG", "{}"))
        hosts = hosts | {
            urlparse(item["registry_url"]).hostname
            for item in config.values()
            if item.get("registry_url")
        }
    if (
        parsed.scheme not in schemes
        or parsed.hostname not in hosts
        or parsed.username is not None
        or parsed.password is not None
        or (not fixture_mode and port not in {None, 443})
    ):
        raise SnapshotValidationError("Snapshot source URL is not approved")
    return value


def _aware_datetime(value, field):
    result = parse_datetime(value) if isinstance(value, str) else None
    if result is None or django_timezone.is_naive(result):
        raise SnapshotValidationError(
            f"Snapshot {field} must be a timezone-aware timestamp"
        )
    return result


def _validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
        raise SnapshotValidationError("Unsupported snapshot schema")
    _digest(snapshot)
    source = snapshot.get("source")
    if source not in FacilitySource.values or snapshot.get("facility_type") != source:
        raise SnapshotValidationError("Snapshot source is invalid")
    try:
        run_id = UUID(snapshot.get("run_id", ""))
    except (TypeError, ValueError, AttributeError) as error:
        raise SnapshotValidationError("Snapshot run ID is invalid") from error
    if str(run_id) != snapshot["run_id"]:
        raise SnapshotValidationError("Snapshot run ID must be canonical")

    fixture_mode = os.environ.get("FACILITY_FIXTURE_MODE", "").lower() == "true"
    registry_url = _checked_url(snapshot.get("registry_url"), fixture_mode)
    document_url = _checked_url(snapshot.get("document_url"), fixture_mode)
    document_sha256 = snapshot.get("document_sha256")
    if not isinstance(document_sha256, str) or not re.fullmatch(
        r"[a-f0-9]{64}", document_sha256
    ):
        raise SnapshotValidationError("Snapshot document hash is invalid")
    raw_key = snapshot.get("raw_key")
    if raw_key != f"raw/{source}/{document_sha256}.pdf":
        raise SnapshotValidationError("Snapshot raw document key is invalid")

    checked_at = _aware_datetime(snapshot.get("checked_at"), "checked_at")
    published_at = snapshot.get("source_published_at")
    if published_at is not None:
        published_at = (
            parse_date(published_at) if isinstance(published_at, str) else None
        )
        if published_at is None:
            raise SnapshotValidationError("Snapshot publication date is invalid")

    records = snapshot.get("records")
    expected_count = snapshot.get("expected_record_count")
    if (
        not isinstance(records, list)
        or not records
        or expected_count != len(records)
        or expected_count > 10000
    ):
        raise SnapshotValidationError("Snapshot record count is invalid")

    keys = set()
    unlocated = 0
    validated = []
    south, north, west, east = SINGAPORE_BOUNDS
    for record in records:
        if not isinstance(record, dict):
            raise SnapshotValidationError("Snapshot contains an invalid facility")
        source_key = record.get("source_key")
        name = record.get("name")
        address = record.get("address")
        postal_code = record.get("postal_code")
        if (
            record.get("source_id") != source
            or record.get("facility_type") != source
            or not isinstance(source_key, str)
            or not source_key
            or len(source_key) > 64
            or source_key in keys
            or not isinstance(name, str)
            or not name.strip()
            or len(name) > 240
            or not isinstance(address, str)
            or not address.strip()
            or not isinstance(postal_code, str)
            or not re.fullmatch(r"\d{6}", postal_code)
        ):
            raise SnapshotValidationError(
                "Snapshot facility identity or address is invalid"
            )
        keys.add(source_key)
        status = record.get("geocode_status")
        latitude, longitude = record.get("latitude"), record.get("longitude")
        if status == "resolved":
            try:
                latitude, longitude = Decimal(str(latitude)), Decimal(str(longitude))
            except (InvalidOperation, TypeError, ValueError) as error:
                raise SnapshotValidationError(
                    "Snapshot coordinates are invalid"
                ) from error
            if (
                not latitude.is_finite()
                or not longitude.is_finite()
                or not (south <= latitude <= north and west <= longitude <= east)
            ):
                raise SnapshotValidationError(
                    "Snapshot coordinates are outside Singapore"
                )
        elif status == "unlocated" and latitude is None and longitude is None:
            unlocated += 1
        else:
            raise SnapshotValidationError(
                "Snapshot geocode status and coordinates conflict"
            )

        licence_no = record.get("licence_no") or ""
        if licence_no and (not isinstance(licence_no, str) or len(licence_no) > 32):
            raise SnapshotValidationError("Snapshot licence number is invalid")
        phone = record.get("phone") or ""
        email = record.get("email") or ""
        website = record.get("website") or ""
        if not all(isinstance(value, str) for value in (phone, email, website)):
            raise SnapshotValidationError("Snapshot contact fields are invalid")
        geocoded_at = _aware_datetime(record.get("geocoded_at"), "geocoded_at")
        approval_fields = {}
        if "approved_animals" in record:
            animals = record["approved_animals"]
            if animals is not None and (
                source != "pet_shop"
                or not isinstance(animals, list)
                or not animals
                or any(
                    not isinstance(animal, str) or animal not in ANIMAL_COLUMNS.values()
                    for animal in animals
                )
                or len(set(animals)) != len(animals)
            ):
                raise SnapshotValidationError("Snapshot animal approvals are invalid")
            approval_fields["approved_animals"] = animals
        if (
            source == "pet_shop"
            and snapshot.get("parser_version") == "2"
            and not approval_fields.get("approved_animals")
        ):
            raise SnapshotValidationError("Snapshot animal approvals are missing")
        validated.append(
            {
                **approval_fields,
                "source_id": source,
                "source_key": source_key,
                "facility_type": source,
                "name": name.strip(),
                "licence_no": licence_no,
                "address": address.strip(),
                "postal_code": postal_code,
                "latitude": latitude if status == "resolved" else None,
                "longitude": longitude if status == "resolved" else None,
                "phone": phone,
                "email": email,
                "website": website,
                "source": dict(FacilitySource.choices)[source],
                "source_url": registry_url,
                "source_document_url": document_url,
                "source_published_at": published_at,
                "last_checked_at": checked_at,
                "geocode_status": status,
                "geocode_query": str(record.get("geocode_query", ""))[:500],
                "geocode_provider": str(record.get("geocode_provider", ""))[:40],
                "geocoded_at": geocoded_at,
                "active": True,
            }
        )
    if snapshot.get("unlocated_count") != unlocated:
        raise SnapshotValidationError("Snapshot unlocated count is invalid")
    return run_id, source, checked_at, published_at, validated, snapshot


def _event(run, kind, detail):
    event_id = uuid5(run.run_id, f"{kind}:{json.dumps(detail, sort_keys=True)}")
    FacilitySyncEvent.objects.get_or_create(
        event_id=event_id,
        defaults={"run": run, "stage": "load", "kind": kind, "detail": detail},
    )


def _record_failure(snapshot, code):
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("source") not in FacilitySource.values
    ):
        return
    try:
        run_id = UUID(snapshot.get("run_id", ""))
    except (TypeError, ValueError, AttributeError):
        return
    now = django_timezone.now()
    with transaction.atomic():
        state, _ = FacilitySourceState.objects.get_or_create(source=snapshot["source"])
        FacilitySourceState.objects.select_for_update().get(pk=state.pk)
        run, _ = FacilitySyncRun.objects.get_or_create(
            run_id=run_id,
            defaults={
                "source": snapshot["source"],
                "status": FacilitySyncRun.Status.FAILED,
                "started_at": now,
            },
        )
        if run.source != snapshot["source"]:
            return
        if run.status in {
            FacilitySyncRun.Status.SUCCEEDED,
            FacilitySyncRun.Status.SUPERSEDED,
        }:
            return
        run.status = (
            FacilitySyncRun.Status.REVIEW_REQUIRED
            if code == "count_drop"
            else FacilitySyncRun.Status.FAILED
        )
        run.stage = "loading"
        run.last_activity_at = now
        run.finished_at = now
        run.error_code = code
        run.error_message = "Snapshot was rejected or could not be applied."
        run.save(
            update_fields=[
                "status",
                "stage",
                "last_activity_at",
                "finished_at",
                "error_code",
                "error_message",
            ]
        )
        _event(run, "load_failed", {"error_code": code})


def _apply_snapshot(
    run_id, source, checked_at, published_at, records, snapshot, *, approve_drop=False
):
    now = django_timezone.now()
    with transaction.atomic():
        state, _ = FacilitySourceState.objects.get_or_create(source=source)
        state = FacilitySourceState.objects.select_for_update().get(pk=source)
        run, _ = FacilitySyncRun.objects.get_or_create(
            run_id=run_id,
            defaults={
                "source": source,
                "status": FacilitySyncRun.Status.RUNNING,
                "started_at": checked_at,
            },
        )
        run = FacilitySyncRun.objects.select_for_update().get(pk=run_id)
        if run.source != source:
            raise SnapshotValidationError(
                "Run ID is already associated with another source"
            )
        if run.status == FacilitySyncRun.Status.SUCCEEDED:
            return {"run_id": str(run_id), "status": run.status, "idempotent": True}
        if run.status == FacilitySyncRun.Status.SUPERSEDED:
            return {"run_id": str(run_id), "status": run.status, "idempotent": True}

        previous = state.latest_successful_run
        if state.last_checked_at and checked_at <= state.last_checked_at:
            run.status = FacilitySyncRun.Status.SUPERSEDED
        elif (
            previous
            and published_at
            and previous.published_at
            and published_at < previous.published_at
        ):
            run.status = FacilitySyncRun.Status.SUPERSEDED
        if run.status == FacilitySyncRun.Status.SUPERSEDED:
            run.finished_at = now
            run.error_code = "stale_snapshot"
            run.error_message = "An older source snapshot was skipped."
            run.save(
                update_fields=["status", "finished_at", "error_code", "error_message"]
            )
            _event(
                run,
                "snapshot_superseded",
                {"document_sha256": snapshot["document_sha256"]},
            )
            return {"run_id": str(run_id), "status": run.status}

        threshold = float(os.environ.get("FACILITY_MAX_DEACTIVATION_FRACTION", "0.2"))
        if not 0 < threshold <= 1:
            raise SnapshotValidationError("Deactivation threshold must be in (0, 1]")
        existing = Facility.objects.filter(source_id=source, active=True)
        count = existing.count()
        removed = existing.exclude(
            source_key__in=[record["source_key"] for record in records]
        ).count()
        if count and removed / count > threshold and not approve_drop:
            raise SnapshotReviewRequired(
                "Snapshot would deactivate too many facilities; staff review is required"
            )

        run.status = FacilitySyncRun.Status.RUNNING
        run.started_at = checked_at
        run.finished_at = None
        run.registry_url = snapshot["registry_url"]
        run.document_url = snapshot["document_url"]
        run.published_at = published_at
        run.document_sha256 = snapshot["document_sha256"]
        run.parsed_count = len(records)
        run.error_code = ""
        run.error_message = ""
        run.save()

        source_keys = []
        inserted = updated = unchanged = 0
        business_fields = (
            "approved_animals",
            "facility_type",
            "name",
            "licence_no",
            "address",
            "postal_code",
            "latitude",
            "longitude",
            "phone",
            "email",
            "website",
            "source",
            "source_url",
            "source_document_url",
            "source_published_at",
            "geocode_status",
            "geocode_query",
            "geocode_provider",
            "geocoded_at",
            "active",
        )
        for defaults in records:
            key = defaults["source_key"]
            source_keys.append(key)
            facility = (
                Facility.objects.select_for_update()
                .filter(source_id=source, source_key=key)
                .first()
            )
            if facility is None:
                Facility.objects.create(
                    **defaults,
                    last_seen_run=run,
                )
                inserted += 1
                continue
            changed = any(
                getattr(facility, field) != defaults[field]
                for field in business_fields
                if field in defaults
            )
            for field, value in defaults.items():
                setattr(facility, field, value)
            facility.last_seen_run = run
            facility.save()
            if changed:
                updated += 1
            else:
                unchanged += 1

        deactivated = (
            Facility.objects.filter(source_id=source, active=True)
            .exclude(source_key__in=source_keys)
            .update(active=False)
        )
        unlocated = snapshot["unlocated_count"]
        run.status = FacilitySyncRun.Status.SUCCEEDED
        run.stage = "complete"
        run.last_activity_at = now
        run.finished_at = now
        run.inserted_count = inserted
        run.updated_count = updated
        run.unchanged_count = unchanged
        run.deactivated_count = deactivated
        run.unlocated_count = unlocated
        run.save(
            update_fields=[
                "status",
                "stage",
                "last_activity_at",
                "finished_at",
                "inserted_count",
                "updated_count",
                "unchanged_count",
                "deactivated_count",
                "unlocated_count",
            ]
        )
        state.latest_successful_run = run
        state.last_checked_at = checked_at
        state.save(
            update_fields=["latest_successful_run", "last_checked_at", "updated_at"]
        )
        _event(
            run,
            "snapshot_applied",
            {
                "inserted": inserted,
                "updated": updated,
                "unchanged": unchanged,
                "deactivated": deactivated,
                "unlocated": unlocated,
            },
        )
        return {
            "run_id": str(run_id),
            "status": run.status,
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
            "deactivated": deactivated,
            "unlocated": unlocated,
        }


def load_snapshot(snapshot, *, approve_drop=False):
    try:
        validated = _validate_snapshot(snapshot)
        return _apply_snapshot(*validated, approve_drop=approve_drop)
    except Exception as error:
        code = (
            "count_drop"
            if isinstance(error, SnapshotReviewRequired)
            else "invalid_snapshot"
            if isinstance(error, SnapshotValidationError)
            else "load_failed"
        )
        try:
            _record_failure(snapshot, code)
        except Exception:
            logging.getLogger(__name__).error(
                "Could not record load failure in database", extra={"error_code": code}
            )
        raise


def load_s3_event(event, s3_client=None):
    bucket = os.environ.get("FACILITY_SYNC_BUCKET")
    if not bucket:
        raise SnapshotValidationError("FACILITY_SYNC_BUCKET is required")
    if s3_client is None:
        s3_client = aws_client("s3")
    records = event.get("Records")
    if not isinstance(records, list) or not records:
        raise SnapshotValidationError("Expected an S3 object-created event")
    results = []
    for record in records:
        if record.get("eventSource") != "aws:s3":
            raise SnapshotValidationError("Unsupported event source")
        bucket_name = record.get("s3", {}).get("bucket", {}).get("name")
        obj = record.get("s3", {}).get("object", {})
        key = unquote_plus(obj.get("key", ""))
        parts = key.split("/")
        if bucket_name == bucket and len(parts) == 4 and parts[0] == "status":
            try:
                status_event = run_status.read_json(s3_client, bucket, key)
                if (
                    not isinstance(status_event, dict)
                    or parts[1] != status_event.get("source")
                    or parts[2] != status_event.get("run_id")
                    or parts[3] != f"{status_event.get('event_id')}.json"
                ):
                    raise SnapshotValidationError(
                        "Status event key and content do not match"
                    )
                run_status.project(status_event)
            except (ValueError, KeyError, TypeError):
                run_status.put_json(
                    s3_client,
                    bucket,
                    f"quarantine/status/{parts[1]}/{parts[2]}/{parts[3]}",
                    {"key": key, "error_code": "invalid_status_event"},
                )
                run_status.metric("QuarantinedMessages", 1)
            run_status.put_json(
                s3_client,
                bucket,
                f"projected/{parts[1]}/{parts[2]}/{parts[3]}",
                {"projected": True},
            )
            continue
        if bucket_name != bucket or len(parts) != 3 or parts[0] != "ready":
            raise SnapshotValidationError(
                "Event does not identify a ready snapshot in the configured bucket"
            )
        source = parts[1]
        filename = parts[2]
        if source not in FacilitySource.values or not filename.endswith(".json"):
            raise SnapshotValidationError("Ready snapshot key is invalid")
        try:
            run_id = str(UUID(filename[:-5]))
        except ValueError as error:
            raise SnapshotValidationError(
                "Ready snapshot key has an invalid run ID"
            ) from error
        if key != f"ready/{source}/{run_id}.json":
            raise SnapshotValidationError("Ready snapshot key is not canonical")
        version = obj.get("versionId")
        snapshot = json.loads(
            s3_client.get_object(
                Bucket=bucket,
                Key=key,
                **({"VersionId": version} if version else {}),
            )["Body"].read()
        )
        if snapshot.get("source") != source or snapshot.get("run_id") != run_id:
            raise SnapshotValidationError("S3 event and snapshot identity do not match")
        approval = run_status.read_json(
            s3_client, bucket, f"approvals/{source}/{run_id}.json"
        )
        try:
            result = load_snapshot(
                snapshot,
                approve_drop=bool(
                    approval
                    and approval.get("snapshot_sha256")
                    == snapshot.get("snapshot_sha256")
                ),
            )
        except SnapshotReviewRequired:
            run_status.fail(
                s3_client,
                bucket,
                source,
                run_id,
                "loading",
                "count_drop",
                permanent=True,
            )
            results.append({"run_id": run_id, "status": "review_required"})
            continue
        except Exception as error:
            try:
                run_status.fail(
                    s3_client,
                    bucket,
                    source,
                    run_id,
                    "loading",
                    type(error).__name__,
                    permanent=isinstance(error, SnapshotValidationError),
                )
            except Exception:
                logging.getLogger(__name__).error(
                    "Could not persist load failure to S3"
                )
            raise
        run_status.put_json(
            s3_client,
            bucket,
            f"loaded/{source}/{run_id}.json",
            {**result, "checked_at": snapshot["checked_at"]},
        )
        results.append(result)
    return {"loaded_snapshots": len(results), "results": results}
