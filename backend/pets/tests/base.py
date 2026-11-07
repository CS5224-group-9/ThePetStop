"""Shared fixtures for the pets API tests.

`PetsAPITestCase` pins the storage backend to "disabled" and patches the four
storage calls, so a developer's backend/.env cannot change behaviour and tests
never touch S3 or the local file folder. The real `storage.delete_on_commit`
runs and calls the patched `delete`; assert file cleanup inside
`self.captureOnCommitCallbacks(execute=True)`.
"""

import uuid
from datetime import date, timedelta
from pathlib import PurePosixPath
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from pets import uploads
from pets.models import HealthRecord, Pet, PetDocument, Reminder
from pets.reminders import due_at_for_date

API = "/api/v1/"
TODAY = date(2026, 10, 30)
CONFLICT_MESSAGE = "This item changed. Refresh and try again."


def days(n: int) -> date:
    """TODAY plus n days."""
    return TODAY + timedelta(days=n)


def does_not_exist(pk) -> str:
    return f'Invalid pk "{pk}" - object does not exist.'


def key_stem(key: str) -> str:
    return PurePosixPath(key).stem


@override_settings(PET_FILES_BACKEND="disabled")
class PetsAPITestCase(APITestCase):
    def setUp(self):
        super().setUp()
        users = get_user_model().objects
        self.alice = users.create_user(username="alice", email="alice@example.test")
        self.bob = users.create_user(username="bob", email="bob@example.test")
        # No Django groups: owning pets is not group-based
        self.merchant = users.create_user(
            username="merchant", email="merchant@example.test"
        )
        self.client.force_authenticate(self.alice)
        # Request bodies are JSON, as the frontend sends them
        self.client.default_format = "json"

        self.presign_put = self.patch(
            "api.storage.presign_put",
            side_effect=lambda key, **kwargs: f"https://files.test/put/{key}",
        )
        self.presign_get = self.patch(
            "api.storage.presign_get",
            side_effect=lambda key, **kwargs: f"https://files.test/get/{key}",
        )
        self.head = self.patch("api.storage.head", return_value=None)
        self.delete = self.patch("api.storage.delete", return_value=None)
        self.today = self.patch("pets.reminders.today_sgt", return_value=TODAY)

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    # Factories

    def make_pet(self, owner, **kwargs):
        kwargs.setdefault("name", "Kopi")
        kwargs.setdefault("species", Pet.DOG)
        return Pet.objects.create(owner=owner, **kwargs)

    def make_record(self, pet, **kwargs):
        kwargs.setdefault("record_type", HealthRecord.VACCINATION)
        kwargs.setdefault("name", "DHPPiL booster")
        kwargs.setdefault("date", days(-30))
        return HealthRecord.objects.create(pet=pet, **kwargs)

    def make_document(self, pet, status=PetDocument.READY, **kwargs):
        doc_id = kwargs.pop("id", uuid.uuid4())
        content_type = kwargs.setdefault("content_type", PetDocument.PDF)
        kwargs.setdefault("title", "Vet report")
        kwargs.setdefault("size_bytes", 3)
        kwargs.setdefault(
            "file_key", uploads.document_key(pet.id, doc_id, content_type)
        )
        if status == PetDocument.READY:
            kwargs.setdefault("uploaded_at", timezone.now())
        return PetDocument.objects.create(id=doc_id, pet=pet, status=status, **kwargs)

    def make_reminder(self, pet, **kwargs):
        kwargs.setdefault("title", "Booster")
        kwargs.setdefault("due_at", due_at_for_date(days(3)))
        return Reminder.objects.create(pet=pet, **kwargs)

    # Assertions

    def assert_error(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.content)
        self.assertEqual(response.json()["error"]["code"], code, response.content)

    def assert_invalid(self, response, field):
        """400 `invalid` with this field in details; returns its messages."""
        self.assert_error(response, 400, "invalid")
        details = response.json()["error"]["details"]
        self.assertIn(field, details, response.content)
        return details[field]

    def deleted_keys(self) -> list[str]:
        return [call.args[0] for call in self.delete.call_args_list]
