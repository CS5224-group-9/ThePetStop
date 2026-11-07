import uuid
from unittest import mock

from django.db import IntegrityError

from pets.models import HealthRecord, PetDocument, Reminder

from .base import API, CONFLICT_MESSAGE, PetsAPITestCase, days

NEXT_DUE_MESSAGE = ["Next due date cannot be before the date of care."]


def records_url(pet) -> str:
    return f"{API}pets/{getattr(pet, 'pk', pet)}/records/"


def record_url(pet, record) -> str:
    return f"{records_url(pet)}{getattr(record, 'pk', record)}/"


class HealthRecordListTests(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(self.alice)
        self.bobs = self.make_pet(self.bob, name="Sesame")

    def test_lists_own_pet_records_newest_first(self):
        self.make_record(self.pet, name="Older", date=days(-60))
        self.make_record(self.pet, name="Newest", date=days(-1))
        self.make_record(self.pet, name="Middle", date=days(-30))
        self.make_record(self.make_pet(self.alice, name="Mochi"), name="Other pet")
        self.make_record(self.bobs, name="Bob's")

        response = self.client.get(records_url(self.pet))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 3)
        names = [r["name"] for r in response.json()["results"]]
        self.assertEqual(names, ["Newest", "Middle", "Older"])

    def test_other_owner_or_malformed_pet_is_404(self):
        self.make_record(self.bobs)
        for url in [
            records_url(self.bobs),
            records_url("zzz"),
            records_url(uuid.uuid4()),
        ]:
            with self.subTest(url):
                self.assert_error(self.client.get(url), 404, "not_found")
        body = {"name": "Rabies", "record_type": "vaccination", "date": str(days(-1))}
        self.assert_error(
            self.client.post(records_url(self.bobs), body), 404, "not_found"
        )
        self.assertEqual(HealthRecord.objects.filter(pet=self.bobs).count(), 1)


class HealthRecordCreateTests(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(self.alice)
        self.bobs = self.make_pet(self.bob, name="Sesame")

    def post(self, **overrides):
        body = {
            "name": "Rabies vaccination",
            "record_type": "vaccination",
            "date": str(days(-10)),
            **overrides,
        }
        return self.client.post(records_url(self.pet), body)

    def test_create_takes_pet_from_url(self):
        response = self.post(
            pet=str(self.bobs.pk),
            next_due=str(days(355)),
            clinic="Sample Veterinary Clinic",
            notes="No reaction",
        )

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(
            list(body),
            [
                "id",
                "pet",
                "name",
                "record_type",
                "date",
                "next_due",
                "clinic",
                "notes",
                "created_at",
                "updated_at",
            ],
        )
        self.assertEqual(body["pet"], str(self.pet.pk))
        self.assertEqual(body["next_due"], str(days(355)))
        self.assertEqual(body["notes"], "No reaction")
        self.assertEqual(HealthRecord.objects.get(pk=body["id"]).pet, self.pet)
        self.assertFalse(HealthRecord.objects.filter(pet=self.bobs).exists())

    def test_next_due_may_be_null_or_the_same_day(self):
        response = self.post(next_due=None)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(response.json()["next_due"])
        response = self.post(date=str(days(-3)), next_due=str(days(-3)))
        self.assertEqual(response.status_code, 201, response.content)

    def test_next_due_creates_no_reminder(self):
        response = self.post(next_due=str(days(30)))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(Reminder.objects.exists())

    def test_validation_errors(self):
        cases = {
            "blank name": ({"name": ""}, "name"),
            "101-char name": ({"name": "n" * 101}, "name"),
            "unknown type": ({"record_type": "surgery"}, "record_type"),
            "date tomorrow": ({"date": str(days(1))}, "date"),
            "next_due before date": (
                {"date": str(days(-5)), "next_due": str(days(-6))},
                "next_due",
            ),
            "101-char clinic": ({"clinic": "c" * 101}, "clinic"),
            "1001-char notes": ({"notes": "n" * 1001}, "notes"),
        }
        for name, (overrides, field) in cases.items():
            with self.subTest(name):
                self.assert_invalid(self.post(**overrides), field)
        self.assertFalse(HealthRecord.objects.exists())

    def test_validation_messages(self):
        messages = self.assert_invalid(self.post(date=str(days(1))), "date")
        self.assertEqual(messages, ["Date of care cannot be in the future."])
        messages = self.assert_invalid(
            self.post(date=str(days(-5)), next_due=str(days(-6))), "next_due"
        )
        self.assertEqual(messages, NEXT_DUE_MESSAGE)

    def test_integrity_error_is_a_clean_conflict(self):
        failure = IntegrityError('Failing row contains (secret, "Rabies")')
        with mock.patch.object(HealthRecord, "save", side_effect=failure):
            response = self.post()
        messages = self.assert_invalid(response, "non_field_errors")
        self.assertEqual(messages, [CONFLICT_MESSAGE])
        self.assertNotIn(b"secret", response.content)


class HealthRecordDetailTests(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(self.alice)
        self.other_pet = self.make_pet(self.alice, name="Mochi")
        self.bobs = self.make_pet(self.bob, name="Sesame")
        self.record = self.make_record(
            self.pet, date=days(-10), next_due=days(20), notes="First dose"
        )
        self.url = record_url(self.pet, self.record)

    def test_get_own_record(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.record.pk))

    def test_record_under_another_pet_is_404(self):
        other_record = self.make_record(self.other_pet)
        bobs_record = self.make_record(self.bobs)
        cases = [
            record_url(self.other_pet, self.record),
            record_url(self.pet, other_record),
            record_url(self.bobs, bobs_record),
            record_url(self.pet, bobs_record),
            record_url(self.pet, "not-a-uuid"),
        ]
        for url in cases:
            with self.subTest(url):
                self.assert_error(self.client.get(url), 404, "not_found")
                self.assert_error(
                    self.client.patch(url, {"notes": "x"}), 404, "not_found"
                )
                self.assert_error(self.client.delete(url), 404, "not_found")
        bobs_record.refresh_from_db()
        self.assertEqual(bobs_record.notes, "")

    def test_patch_notes(self):
        response = self.client.patch(self.url, {"notes": "Second dose booked"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["notes"], "Second dose booked")
        self.record.refresh_from_db()
        self.assertEqual(self.record.notes, "Second dose booked")
        self.assertEqual(self.record.next_due, days(20))

    def test_patch_dates_are_checked_against_stored_values(self):
        response = self.client.patch(self.url, {"next_due": str(days(-11))})
        self.assertEqual(self.assert_invalid(response, "next_due"), NEXT_DUE_MESSAGE)
        # A date after the stored next_due (which must be in the past, since a
        # date of care cannot be in the future)
        HealthRecord.objects.filter(pk=self.record.pk).update(next_due=days(-5))
        response = self.client.patch(self.url, {"date": str(days(-4))})
        self.assertEqual(self.assert_invalid(response, "next_due"), NEXT_DUE_MESSAGE)
        self.record.refresh_from_db()
        self.assertEqual(
            (self.record.date, self.record.next_due), (days(-10), days(-5))
        )

    def test_patch_ignores_body_pet(self):
        for target in [self.bobs, self.other_pet]:
            with self.subTest(target.name):
                response = self.client.patch(
                    self.url, {"pet": str(target.pk), "notes": target.name}
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()["pet"], str(self.pet.pk))
                self.record.refresh_from_db()
                self.assertEqual(self.record.pet_id, self.pet.pk)
                self.assertEqual(self.record.notes, target.name)

    def test_put_is_not_allowed(self):
        body = {"name": "x", "record_type": "other", "date": str(days(-1))}
        self.assert_error(self.client.put(self.url, body), 405, "method_not_allowed")

    def test_delete_keeps_linked_reminder_and_document(self):
        reminder = self.make_reminder(self.pet, health_record=self.record)
        document = self.make_document(self.pet, health_record=self.record)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(HealthRecord.objects.filter(pk=self.record.pk).exists())
        reminder.refresh_from_db()
        document.refresh_from_db()
        self.assertIsNone(reminder.health_record)
        self.assertIsNone(document.health_record)
        self.assertEqual(document.status, PetDocument.READY)
        self.delete.assert_not_called()

    def test_integrity_error_on_patch_is_a_clean_conflict(self):
        failure = IntegrityError("Failing row contains (secret notes)")
        with mock.patch.object(HealthRecord, "save", side_effect=failure):
            response = self.client.patch(self.url, {"notes": "secret notes"})
        messages = self.assert_invalid(response, "non_field_errors")
        self.assertEqual(messages, [CONFLICT_MESSAGE])
        self.assertNotIn(b"secret", response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.notes, "First dose")
