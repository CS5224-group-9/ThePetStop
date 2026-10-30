import re
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from api.storage import StorageUnavailable, StoredObject
from pets.models import Pet, PetDocument

from .base import API, PetsAPITestCase


def documents_url(pet) -> str:
    return f"{API}pets/{getattr(pet, 'pk', pet)}/documents/"


def document_url(pet, doc) -> str:
    return f"{documents_url(pet)}{getattr(doc, 'pk', doc)}/"


def complete_url(pet, doc) -> str:
    return f"{document_url(pet, doc)}complete/"


DOCUMENT_FIELDS = [
    "id",
    "pet",
    "health_record",
    "title",
    "content_type",
    "size_bytes",
    "status",
    "uploaded_at",
    "created_at",
    "download_url",
]


class DocumentUploadRequestTests(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(self.alice)
        self.bobs = self.make_pet(self.bob, name="Sesame")

    def post(self, pet=None, **overrides):
        body = {
            "title": "Rabies certificate",
            "filename": "kopi-rabies-certificate.pdf",
            "content_type": "application/pdf",
            "size_bytes": 300045,
            **overrides,
        }
        return self.client.post(documents_url(pet or self.pet), body)

    def test_request_creates_a_pending_document_and_ticket(self):
        response = self.post()

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(list(body), ["document", "upload_url", "upload_headers"])
        document = body["document"]
        self.assertEqual(list(document), DOCUMENT_FIELDS)
        self.assertEqual(document["status"], "pending")
        self.assertIsNone(document["uploaded_at"])
        self.assertIsNone(document["download_url"])
        self.assertEqual(document["pet"], str(self.pet.pk))
        self.assertEqual(document["size_bytes"], 300045)
        self.assertEqual(body["upload_headers"], {"Content-Type": "application/pdf"})

        self.presign_put.assert_called_once()
        key = self.presign_put.call_args.args[0]
        self.assertRegex(
            key,
            rf"^pets/{self.pet.pk}/documents/{re.escape(document['id'])}\.pdf$",
        )
        self.assertEqual(
            self.presign_put.call_args.kwargs,
            {
                "content_type": "application/pdf",
                "size_bytes": 300045,
                "expires_in": 900,
            },
        )
        self.assertEqual(body["upload_url"], f"https://files.test/put/{key}")
        # Keys carry no user-supplied names
        self.assertNotIn("rabies", key.lower())
        self.assertNotIn("kopi", key.lower())
        doc = PetDocument.objects.get(pk=document["id"])
        self.assertEqual((doc.status, doc.file_key), (PetDocument.PENDING, key))

    def test_health_record_of_the_same_pet(self):
        record = self.make_record(self.pet)
        response = self.post(health_record=str(record.pk))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["document"]["health_record"], str(record.pk))

    def test_validation_errors(self):
        bobs_record = self.make_record(self.bobs)
        other_record = self.make_record(self.make_pet(self.alice, name="Mochi"))
        cases = {
            "gif": ({"content_type": "image/gif"}, "content_type"),
            "empty file": ({"size_bytes": 0}, "size_bytes"),
            "over 10 MiB": ({"size_bytes": 10485761}, "size_bytes"),
            "blank title": ({"title": ""}, "title"),
            "151-char title": ({"title": "t" * 151}, "title"),
            "256-char filename": ({"filename": "f" * 252 + ".pdf"}, "filename"),
            "bob's record": ({"health_record": str(bobs_record.pk)}, "health_record"),
            "other pet's record": (
                {"health_record": str(other_record.pk)},
                "health_record",
            ),
        }
        for name, (overrides, field) in cases.items():
            with self.subTest(name):
                self.assert_invalid(self.post(**overrides), field)
        self.assertFalse(PetDocument.objects.exists())
        self.presign_put.assert_not_called()

    def test_ten_mib_is_accepted(self):
        response = self.post(size_bytes=10485760, content_type="image/png")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(self.presign_put.call_args.args[0].endswith(".png"))

    def test_other_owner_pet_is_404(self):
        self.assert_error(self.post(pet=self.bobs), 404, "not_found")
        self.assertFalse(PetDocument.objects.exists())

    def test_storage_unavailable_creates_nothing(self):
        self.presign_put.side_effect = StorageUnavailable
        self.assert_error(self.post(), 503, "storage_unavailable")
        self.assertFalse(PetDocument.objects.exists())

    def test_request_purges_stale_pending_documents(self):
        stale = self.make_document(self.pet, status=PetDocument.PENDING)
        fresh = self.make_document(self.pet, status=PetDocument.PENDING)
        bobs_stale = self.make_document(self.bobs, status=PetDocument.PENDING)
        two_hours_ago = timezone.now() - timedelta(hours=2)
        PetDocument.objects.filter(pk__in=[stale.pk, bobs_stale.pk]).update(
            created_at=two_hours_ago
        )
        PetDocument.objects.filter(pk=fresh.pk).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )
        Pet.objects.filter(pk=self.bobs.pk).update(
            pending_photo_key=f"pets/{self.bobs.pk}/photos/{uuid.uuid4()}.jpg",
            pending_photo_requested_at=two_hours_ago,
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post()

        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(PetDocument.objects.filter(pk=stale.pk).exists())
        self.assertTrue(PetDocument.objects.filter(pk=fresh.pk).exists())
        self.assertTrue(PetDocument.objects.filter(pk=bobs_stale.pk).exists())
        self.assertNotEqual(Pet.objects.get(pk=self.bobs.pk).pending_photo_key, "")
        self.assertEqual(self.deleted_keys(), [stale.file_key])
        # The new upload itself stays pending
        new = PetDocument.objects.get(pk=response.json()["document"]["id"])
        self.assertEqual(new.status, PetDocument.PENDING)


class DocumentCompleteTests(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(self.alice)
        self.doc = self.make_document(
            self.pet, status=PetDocument.PENDING, size_bytes=300045
        )
        self.url = complete_url(self.pet, self.doc)

    def complete(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url)

    def test_matching_upload_becomes_ready(self):
        self.head.return_value = StoredObject(300045, "application/pdf")

        response = self.complete()

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(list(body), DOCUMENT_FIELDS)
        self.assertEqual(body["status"], "ready")
        self.assertIsNotNone(body["uploaded_at"])
        self.assertEqual(
            body["download_url"], f"https://files.test/get/{self.doc.file_key}"
        )
        self.head.assert_called_once_with(self.doc.file_key)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, PetDocument.READY)
        self.assertIsNotNone(self.doc.uploaded_at)

        # Completing again is idempotent and makes no storage call
        self.head.reset_mock()
        response = self.complete()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "ready")
        self.head.assert_not_called()
        self.delete.assert_not_called()

    def test_content_type_parameters_are_ignored(self):
        self.head.return_value = StoredObject(300045, "application/pdf; charset=binary")
        response = self.complete()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "ready")

    def test_missing_upload_is_409_and_stays_pending(self):
        self.head.return_value = None
        response = self.complete()
        self.assert_error(response, 409, "upload_incomplete")
        self.assertEqual(
            response.json()["error"]["message"],
            "The file has not finished uploading. Try again.",
        )
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, PetDocument.PENDING)
        self.delete.assert_not_called()

    def test_mismatched_upload_is_discarded(self):
        cases = {
            "size": StoredObject(300044, "application/pdf"),
            "type": StoredObject(300045, "image/png"),
        }
        for name, stored in cases.items():
            with self.subTest(name):
                doc = self.make_document(
                    self.pet, status=PetDocument.PENDING, size_bytes=300045
                )
                self.head.return_value = stored
                self.delete.reset_mock()
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(complete_url(self.pet, doc))
                self.assert_error(response, 400, "upload_invalid")
                self.assertFalse(PetDocument.objects.filter(pk=doc.pk).exists())
                self.delete.assert_called_once_with(doc.file_key)

    def test_storage_unavailable_is_503(self):
        self.head.side_effect = StorageUnavailable
        self.assert_error(self.complete(), 503, "storage_unavailable")
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, PetDocument.PENDING)

    def test_concurrent_delete_is_404_without_resurrection(self):
        def delete_meanwhile(key):
            PetDocument.objects.filter(pk=self.doc.pk).delete()
            return StoredObject(300045, "application/pdf")

        self.head.side_effect = delete_meanwhile
        self.assert_error(self.complete(), 404, "not_found")
        self.assertFalse(PetDocument.objects.filter(pk=self.doc.pk).exists())

    def test_concurrent_delete_of_a_mismatch_deletes_nothing_more(self):
        def delete_meanwhile(key):
            PetDocument.objects.filter(pk=self.doc.pk).delete()
            return StoredObject(1, "application/pdf")

        self.head.side_effect = delete_meanwhile
        self.assert_error(self.complete(), 400, "upload_invalid")
        # Whoever deleted the row owns the file cleanup
        self.delete.assert_not_called()

    def test_other_owner_or_other_pet_is_404(self):
        other_pet = self.make_pet(self.alice, name="Mochi")
        bobs = self.make_pet(self.bob, name="Sesame")
        bobs_doc = self.make_document(bobs, status=PetDocument.PENDING)
        for url in [
            complete_url(other_pet, self.doc),
            complete_url(bobs, bobs_doc),
            complete_url(self.pet, bobs_doc),
            complete_url(self.pet, "nope"),
        ]:
            with self.subTest(url):
                self.assert_error(self.client.post(url), 404, "not_found")
        self.head.assert_not_called()


class DocumentReadWriteTests(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(self.alice)
        self.other_pet = self.make_pet(self.alice, name="Mochi")
        self.bobs = self.make_pet(self.bob, name="Sesame")
        self.ready = self.make_document(self.pet, title="Blood test")
        self.pending = self.make_document(self.pet, status=PetDocument.PENDING)

    def test_list_shows_ready_documents_with_download_urls(self):
        png = self.make_document(self.pet, title="X-ray", content_type="image/png")
        PetDocument.objects.filter(pk=png.pk).update(
            uploaded_at=timezone.now() + timedelta(minutes=1)
        )
        self.make_document(self.other_pet)

        response = self.client.get(documents_url(self.pet))

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual([d["title"] for d in results], ["X-ray", "Blood test"])
        self.assertEqual(
            results[1]["download_url"], f"https://files.test/get/{self.ready.file_key}"
        )
        self.presign_get.assert_any_call(
            self.ready.file_key,
            content_type="application/pdf",
            disposition='attachment; filename="pet-document.pdf"',
            expires_in=300,
        )
        self.presign_get.assert_any_call(
            png.file_key,
            content_type="image/png",
            disposition='attachment; filename="pet-document.png"',
            expires_in=300,
        )
        for call in self.presign_get.call_args_list:
            self.assertNotEqual(call.args[0], self.pending.file_key)

    def test_detail_shows_only_ready_documents(self):
        response = self.client.get(document_url(self.pet, self.ready))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Blood test")
        self.assert_error(
            self.client.get(document_url(self.pet, self.pending)), 404, "not_found"
        )

    def test_patch_title_and_health_record(self):
        record = self.make_record(self.pet)
        url = document_url(self.pet, self.ready)
        response = self.client.patch(
            url, {"title": "CBC results", "health_record": str(record.pk)}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.ready.refresh_from_db()
        self.assertEqual(
            (self.ready.title, self.ready.health_record), ("CBC results", record)
        )

        other_record = self.make_record(self.other_pet)
        response = self.client.patch(url, {"health_record": str(other_record.pk)})
        self.assert_invalid(response, "health_record")
        response = self.client.patch(url, {"title": ""})
        self.assert_invalid(response, "title")
        self.ready.refresh_from_db()
        self.assertEqual(
            (self.ready.title, self.ready.health_record), ("CBC results", record)
        )

    def test_patch_pending_is_404(self):
        response = self.client.patch(
            document_url(self.pet, self.pending), {"title": "New"}
        )
        self.assert_error(response, 404, "not_found")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.title, "Vet report")

    def test_patch_ignores_read_only_fields(self):
        before = PetDocument.objects.get(pk=self.ready.pk)
        response = self.client.patch(
            document_url(self.pet, self.ready),
            {
                "pet": str(self.bobs.pk),
                "status": "pending",
                "content_type": "image/png",
                "size_bytes": 1,
                "file_key": "x",
                "uploaded_at": "2020-01-01T00:00:00Z",
                "title": "Renamed",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        after = PetDocument.objects.get(pk=self.ready.pk)
        self.assertEqual(after.title, "Renamed")
        for field in [
            "pet_id",
            "status",
            "content_type",
            "size_bytes",
            "file_key",
            "uploaded_at",
        ]:
            with self.subTest(field):
                self.assertEqual(getattr(after, field), getattr(before, field))

    def test_put_is_not_allowed(self):
        response = self.client.put(document_url(self.pet, self.ready), {"title": "x"})
        self.assert_error(response, 405, "method_not_allowed")

    def test_delete_pending_and_ready(self):
        for doc in [self.pending, self.ready]:
            with self.subTest(doc.status):
                self.delete.reset_mock()
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.delete(document_url(self.pet, doc))
                self.assertEqual(response.status_code, 204)
                self.assertFalse(PetDocument.objects.filter(pk=doc.pk).exists())
                self.delete.assert_called_once_with(doc.file_key)

    def test_other_owner_or_other_pet_is_404(self):
        bobs_doc = self.make_document(self.bobs)
        self.assert_error(self.client.get(documents_url(self.bobs)), 404, "not_found")
        cases = [
            document_url(self.bobs, bobs_doc),
            document_url(self.pet, bobs_doc),
            document_url(self.other_pet, self.ready),
            document_url(self.pet, "not-a-uuid"),
        ]
        for url in cases:
            with self.subTest(url):
                self.assert_error(self.client.get(url), 404, "not_found")
                self.assert_error(
                    self.client.patch(url, {"title": "x"}), 404, "not_found"
                )
                with self.captureOnCommitCallbacks(execute=True):
                    self.assert_error(self.client.delete(url), 404, "not_found")
        self.assertTrue(PetDocument.objects.filter(pk=bobs_doc.pk).exists())
        self.assertTrue(PetDocument.objects.filter(pk=self.ready.pk).exists())
        self.delete.assert_not_called()


class DocumentsWithoutStorageTests(APITestCase):
    """No storage patches: the disabled backend answers for itself."""

    @override_settings(PET_FILES_BACKEND="disabled")
    def test_upload_is_503_and_listing_still_works(self):
        user = get_user_model().objects.create_user(username="carol")
        self.client.force_authenticate(user)
        pet = Pet.objects.create(owner=user, name="Biscuit", species=Pet.DOG)
        ready = PetDocument.objects.create(
            pet=pet,
            title="Report",
            file_key=f"pets/{pet.pk}/documents/{uuid.uuid4()}.pdf",
            content_type=PetDocument.PDF,
            size_bytes=3,
            status=PetDocument.READY,
            uploaded_at=timezone.now(),
        )

        with mock.patch("pets.uploads.purge_stale_pending") as purge:
            response = self.client.post(
                f"{API}pets/{pet.pk}/documents/",
                {"title": "Scan", "content_type": "application/pdf", "size_bytes": 3},
                format="json",
            )

        self.assertEqual(response.status_code, 503, response.content)
        self.assertEqual(response.json()["error"]["code"], "storage_unavailable")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(
            list(PetDocument.objects.values_list("pk", flat=True)), [ready.pk]
        )
        # The 503 comes before any DB work, purging included
        purge.assert_not_called()

        response = self.client.get(f"{API}pets/{pet.pk}/documents/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["results"][0]["download_url"])
