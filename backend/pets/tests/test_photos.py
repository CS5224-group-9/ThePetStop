import os
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from api import storage
from api.storage import StorageUnavailable, StoredObject
from pets.models import Pet

from .base import API, PetsAPITestCase, key_stem

UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
PENDING_FIELDS = (
    "pending_photo_key",
    "pending_photo_content_type",
    "pending_photo_size_bytes",
    "pending_photo_requested_at",
)
PHOTO_FIELDS = ("photo_key", "photo_content_type", *PENDING_FIELDS)


def pet_url(pet) -> str:
    return f"{API}pets/{getattr(pet, 'pk', pet)}/"


def pending(pet):
    return tuple(getattr(pet, field) for field in PENDING_FIELDS)


class PhotoTestCase(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.old_key = f"pets/{uuid.uuid4()}/photos/{uuid.uuid4()}.png"
        self.pet = self.make_pet(
            self.alice, photo_key=self.old_key, photo_content_type="image/png"
        )
        self.upload_url = f"{pet_url(self.pet)}photo-upload/"
        self.complete_url = f"{self.upload_url}complete/"
        self.photo_url = f"{pet_url(self.pet)}photo/"

    def request_upload(self, content_type="image/jpeg", size_bytes=1000):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.upload_url,
                {"content_type": content_type, "size_bytes": size_bytes},
            )
        self.assertEqual(response.status_code, 200, response.content)
        return self.presign_put.call_args.args[0]

    def complete(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.complete_url)


class PhotoUploadRequestTests(PhotoTestCase):
    def test_request_returns_a_ticket_and_records_the_pending_upload(self):
        before = timezone.now()
        response = self.client.post(
            self.upload_url, {"content_type": "image/jpeg", "size_bytes": 1000}
        )

        self.assertEqual(response.status_code, 200, response.content)
        key = self.presign_put.call_args.args[0]
        self.assertRegex(key, rf"^pets/{self.pet.pk}/photos/{UUID_PATTERN}\.jpg$")
        self.assertEqual(
            response.json(),
            {
                "upload_url": f"https://files.test/put/{key}",
                "upload_headers": {"Content-Type": "image/jpeg"},
            },
        )
        self.presign_put.assert_called_once_with(
            key, content_type="image/jpeg", size_bytes=1000, expires_in=900
        )
        self.pet.refresh_from_db()
        self.assertEqual(pending(self.pet)[:3], (key, "image/jpeg", 1000))
        self.assertGreaterEqual(self.pet.pending_photo_requested_at, before)
        # The completed photo is unchanged and pending photos are never exposed
        self.assertEqual(self.pet.photo_key, self.old_key)
        body = self.client.get(pet_url(self.pet)).json()
        self.assertEqual(body["photo_version"], key_stem(self.old_key))

    def test_png_is_accepted(self):
        key = self.request_upload("image/png", 5242880)
        self.assertTrue(key.endswith(".png"))

    def test_invalid_requests(self):
        cases = {
            "pdf": (
                {"content_type": "application/pdf", "size_bytes": 1000},
                "content_type",
            ),
            "gif": ({"content_type": "image/gif", "size_bytes": 1000}, "content_type"),
            "empty": ({"content_type": "image/jpeg", "size_bytes": 0}, "size_bytes"),
            "over 5 MiB": (
                {"content_type": "image/jpeg", "size_bytes": 5242881},
                "size_bytes",
            ),
        }
        for name, (body, field) in cases.items():
            with self.subTest(name):
                self.assert_invalid(self.client.post(self.upload_url, body), field)
        self.presign_put.assert_not_called()
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.pending_photo_key, "")

    def test_second_request_replaces_the_pending_upload(self):
        first = self.request_upload()
        self.delete.assert_not_called()
        second = self.request_upload()
        self.assertNotEqual(first, second)
        self.delete.assert_called_once_with(first)
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.pending_photo_key, second)

    def test_storage_unavailable_changes_nothing(self):
        self.presign_put.side_effect = StorageUnavailable
        response = self.client.post(
            self.upload_url, {"content_type": "image/jpeg", "size_bytes": 1000}
        )
        self.assert_error(response, 503, "storage_unavailable")
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.pending_photo_key, "")


class PhotoCompleteTests(PhotoTestCase):
    def test_matching_upload_replaces_the_photo(self):
        key = self.request_upload()
        self.head.return_value = StoredObject(1000, "image/jpeg")

        response = self.complete()

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["id"], str(self.pet.pk))
        self.assertEqual(body["photo_url"], f"https://files.test/get/{key}")
        self.assertEqual(body["photo_version"], key_stem(key))
        self.presign_get.assert_called_with(
            key, content_type="image/jpeg", disposition="inline", expires_in=3600
        )
        self.head.assert_called_once_with(key)
        self.delete.assert_called_once_with(self.old_key)
        self.pet.refresh_from_db()
        self.assertEqual(
            (self.pet.photo_key, self.pet.photo_content_type), (key, "image/jpeg")
        )
        self.assertEqual(pending(self.pet), ("", "", None, None))

    def test_without_a_pending_upload_is_409(self):
        self.assert_error(self.complete(), 409, "upload_incomplete")
        self.head.assert_not_called()

    def test_missing_upload_is_409_and_keeps_the_pending_upload(self):
        key = self.request_upload()
        self.head.return_value = None
        self.assert_error(self.complete(), 409, "upload_incomplete")
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.pending_photo_key, key)
        self.assertEqual(self.pet.photo_key, self.old_key)
        self.delete.assert_not_called()

    def test_mismatched_upload_is_discarded(self):
        key = self.request_upload()
        self.head.return_value = StoredObject(999, "image/jpeg")

        self.assert_error(self.complete(), 400, "upload_invalid")

        self.pet.refresh_from_db()
        self.assertEqual(pending(self.pet), ("", "", None, None))
        self.assertEqual(self.pet.photo_key, self.old_key)
        self.delete.assert_called_once_with(key)

    def test_storage_unavailable_is_503(self):
        key = self.request_upload()
        self.head.side_effect = StorageUnavailable
        self.assert_error(self.complete(), 503, "storage_unavailable")
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.pending_photo_key, key)

    def test_pet_deleted_meanwhile_is_404(self):
        self.request_upload()

        def delete_meanwhile(key):
            Pet.objects.filter(pk=self.pet.pk).delete()
            return StoredObject(1000, "image/jpeg")

        self.head.side_effect = delete_meanwhile
        self.assert_error(self.complete(), 404, "not_found")
        self.assertFalse(Pet.objects.filter(pk=self.pet.pk).exists())

    def test_upload_replaced_meanwhile_is_409(self):
        self.request_upload()
        newer = f"pets/{self.pet.pk}/photos/{uuid.uuid4()}.jpg"

        def replace_meanwhile(key):
            Pet.objects.filter(pk=self.pet.pk).update(pending_photo_key=newer)
            return StoredObject(1000, "image/jpeg")

        self.head.side_effect = replace_meanwhile
        self.assert_error(self.complete(), 409, "upload_incomplete")
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.pending_photo_key, newer)
        self.assertEqual(self.pet.photo_key, self.old_key)
        self.delete.assert_not_called()


class PhotoDeleteTests(PhotoTestCase):
    def test_delete_clears_all_photo_fields(self):
        key = self.request_upload()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(self.photo_url)
        self.assertEqual(response.status_code, 204)
        self.assertCountEqual(self.deleted_keys(), [self.old_key, key])
        self.pet.refresh_from_db()
        self.assertEqual(
            tuple(getattr(self.pet, f) for f in PHOTO_FIELDS),
            ("", "", "", "", None, None),
        )
        body = self.client.get(pet_url(self.pet)).json()
        self.assertEqual((body["photo_url"], body["photo_version"]), (None, None))

    def test_delete_without_a_photo_is_204(self):
        pet = self.make_pet(self.alice, name="Mochi")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(f"{pet_url(pet)}photo/")
        self.assertEqual(response.status_code, 204)
        self.delete.assert_not_called()


class PhotoOwnershipTests(PhotoTestCase):
    def test_other_owner_pet_is_404_on_every_photo_route(self):
        bobs = self.make_pet(
            self.bob,
            name="Sesame",
            photo_key=f"pets/{uuid.uuid4()}/photos/{uuid.uuid4()}.jpg",
            photo_content_type="image/jpeg",
            pending_photo_key=f"pets/{uuid.uuid4()}/photos/{uuid.uuid4()}.jpg",
            pending_photo_content_type="image/jpeg",
            pending_photo_size_bytes=1000,
        )
        self.head.return_value = StoredObject(1000, "image/jpeg")
        body = {"content_type": "image/jpeg", "size_bytes": 1000}
        for method, path in [
            ("post", "photo-upload/"),
            ("post", "photo-upload/complete/"),
            ("delete", "photo/"),
        ]:
            with self.subTest(path), self.captureOnCommitCallbacks(execute=True):
                response = getattr(self.client, method)(f"{pet_url(bobs)}{path}", body)
                self.assert_error(response, 404, "not_found")
        before = tuple(getattr(bobs, f) for f in PHOTO_FIELDS)
        bobs.refresh_from_db()
        self.assertEqual(tuple(getattr(bobs, f) for f in PHOTO_FIELDS), before)
        self.presign_put.assert_not_called()
        self.head.assert_not_called()
        self.delete.assert_not_called()

    def test_pets_without_photos_have_null_photo_fields(self):
        self.make_pet(self.alice, name="Mochi")
        results = self.client.get(f"{API}pets/").json()["results"]
        by_name = {p["name"]: p for p in results}
        self.assertEqual(
            (by_name["Mochi"]["photo_url"], by_name["Mochi"]["photo_version"]),
            (None, None),
        )
        self.assertEqual(by_name["Kopi"]["photo_version"], key_stem(self.old_key))


@override_settings(
    PET_FILES_BACKEND="s3",
    PET_FILES_BUCKET="test-bucket",
    PET_FILES_REGION="ap-southeast-1",
    PET_FILES_ENDPOINT_URL="",
)
class PhotoUrlWithoutCredentialsTests(APITestCase):
    """No storage patches: S3 presigning without credentials degrades to null."""

    def setUp(self):
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for name in [name for name in os.environ if name.startswith("AWS_")]:
            del os.environ[name]
        os.environ.update(
            {
                "AWS_CONFIG_FILE": os.devnull,
                "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
                "AWS_EC2_METADATA_DISABLED": "true",
                "BOTO_CONFIG": os.devnull,
            }
        )
        storage._s3_client.cache_clear()
        self.addCleanup(storage._s3_client.cache_clear)

    def test_listing_works_with_a_null_photo_url(self):
        user = get_user_model().objects.create_user(username="carol")
        self.client.force_authenticate(user)
        version = str(uuid.uuid4())
        Pet.objects.create(
            owner=user,
            name="Biscuit",
            species=Pet.DOG,
            photo_key=f"pets/{uuid.uuid4()}/photos/{version}.jpg",
            photo_content_type="image/jpeg",
        )

        with self.assertLogs("api.storage", "WARNING") as logs:
            response = self.client.get(f"{API}pets/")

        self.assertEqual(response.status_code, 200, response.content)
        pet = response.json()["results"][0]
        self.assertIsNone(pet["photo_url"])
        self.assertEqual(pet["photo_version"], version)
        self.assertEqual(
            logs.output,
            ["WARNING:api.storage:Pet file presign_get failed: NoCredentialsError"],
        )
