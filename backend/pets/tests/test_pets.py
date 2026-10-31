import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError
from django.utils import timezone

from api.storage import StorageUnavailable
from pets.models import HealthRecord, Pet, PetDocument, Reminder

from .base import API, CONFLICT_MESSAGE, TODAY, PetsAPITestCase, days

PETS = f"{API}pets/"
MICROCHIP_MESSAGE = ["Enter exactly 15 digits, or leave it blank."]
WIRE_FIELDS = [
    "id",
    "name",
    "species",
    "breed",
    "sex",
    "date_of_birth",
    "microchip_no",
    "allergies",
    "diet_notes",
    "weight_kg",
    "photo_url",
    "photo_version",
    "created_at",
    "updated_at",
]


def detail(pet) -> str:
    return f"{PETS}{getattr(pet, 'pk', pet)}/"


class PetListTests(PetsAPITestCase):
    def test_anonymous_gets_401(self):
        self.client.force_authenticate(None)
        self.assert_error(self.client.get(PETS), 401, "not_authenticated")
        response = self.client.post(PETS, {"name": "Kopi", "species": "dog"})
        self.assert_error(response, 401, "not_authenticated")
        self.assertFalse(Pet.objects.exists())

    def test_lists_only_own_pets_oldest_first(self):
        mochi = self.make_pet(self.alice, name="Mochi")
        kopi = self.make_pet(self.alice, name="Kopi")
        self.make_pet(self.bob, name="Sesame")
        now = timezone.now()
        Pet.objects.filter(pk=mochi.pk).update(created_at=now - timedelta(days=1))
        Pet.objects.filter(pk=kopi.pk).update(created_at=now - timedelta(days=2))

        response = self.client.get(PETS)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(list(body), ["count", "next", "previous", "results"])
        self.assertEqual(body["count"], 2)
        self.assertIsNone(body["next"])
        self.assertEqual([p["name"] for p in body["results"]], ["Kopi", "Mochi"])
        self.assertEqual(list(body["results"][0]), WIRE_FIELDS)

    def test_merchant_can_create_and_list_own_pets(self):
        self.make_pet(self.alice)
        self.client.force_authenticate(self.merchant)
        response = self.client.post(PETS, {"name": "Biscuit", "species": "dog"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Pet.objects.get(pk=response.json()["id"]).owner, self.merchant)
        names = [p["name"] for p in self.client.get(PETS).json()["results"]]
        self.assertEqual(names, ["Biscuit"])

    def test_listing_does_not_purge_stale_uploads(self):
        # GET pets/ stays read-only: purging happens only on upload requests
        pet = self.make_pet(
            self.alice,
            pending_photo_key=f"pets/{uuid.uuid4()}/photos/{uuid.uuid4()}.jpg",
            pending_photo_content_type="image/jpeg",
            pending_photo_size_bytes=10,
            pending_photo_requested_at=timezone.now() - timedelta(hours=2),
        )
        stale = self.make_document(pet, status=PetDocument.PENDING)
        PetDocument.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.get(PETS).status_code, 200)

        self.assertTrue(PetDocument.objects.filter(pk=stale.pk).exists())
        self.assertNotEqual(Pet.objects.get(pk=pet.pk).pending_photo_key, "")
        self.delete.assert_not_called()


class PetCreateTests(PetsAPITestCase):
    def post(self, body):
        return self.client.post(PETS, body, format="json")

    def test_minimal_create_uses_defaults_and_ignores_owner(self):
        response = self.post({"name": "Kopi", "species": "dog", "owner": self.bob.pk})

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(list(body), WIRE_FIELDS)
        self.assertEqual(body["name"], "Kopi")
        self.assertEqual(body["species"], "dog")
        expected = {
            "breed": "",
            "sex": "unknown",
            "date_of_birth": None,
            "microchip_no": None,
            "allergies": [],
            "diet_notes": "",
            "weight_kg": None,
            "photo_url": None,
            "photo_version": None,
        }
        self.assertEqual({k: body[k] for k in expected}, expected)
        self.assertEqual(Pet.objects.get(pk=body["id"]).owner, self.alice)

    def test_full_body_round_trips(self):
        body = {
            "name": "Nemo",
            "species": "fish",
            "breed": "Clownfish",
            "sex": "female",
            "date_of_birth": "2024-02-15",
            "microchip_no": "702000000000011",
            "allergies": ["Chicken", "Beef"],
            "diet_notes": "Marine flakes",
            "weight_kg": 12.5,
        }

        response = self.post(body)

        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual({k: data[k] for k in body}, body)
        self.assertIsInstance(data["weight_kg"], float)
        self.assertIn(b'"weight_kg":12.5', response.content)
        pet = Pet.objects.get(pk=data["id"])
        self.assertEqual(pet.weight_kg, Decimal("12.50"))
        self.assertEqual(pet.species, Pet.FISH)

    def test_validation_errors(self):
        long_allergy = "a" * 51
        cases = {
            "blank name": ({"name": ""}, "name"),
            "51-char name": ({"name": "x" * 51}, "name"),
            "unknown species": ({"species": "dragon"}, "species"),
            "unknown sex": ({"sex": "x"}, "sex"),
            "81-char breed": ({"breed": "b" * 81}, "breed"),
            "born tomorrow": ({"date_of_birth": str(days(1))}, "date_of_birth"),
            "allergies not a list": ({"allergies": "Chicken"}, "allergies"),
            "blank allergy": ({"allergies": [""]}, "allergies"),
            "51-char allergy": ({"allergies": [long_allergy]}, "allergies"),
            "21 allergies": (
                {"allergies": [f"a{i}" for i in range(21)]},
                "allergies",
            ),
            "501-char diet": ({"diet_notes": "d" * 501}, "diet_notes"),
            "zero weight": ({"weight_kg": 0}, "weight_kg"),
            "negative weight": ({"weight_kg": -1}, "weight_kg"),
            "too heavy": ({"weight_kg": 500.01}, "weight_kg"),
            "three decimals": ({"weight_kg": 12.345}, "weight_kg"),
        }
        for name, (overrides, field) in cases.items():
            with self.subTest(name):
                body = {"name": "Kopi", "species": "dog", **overrides}
                self.assert_invalid(self.post(body), field)
        self.assertFalse(Pet.objects.exists())

    def test_validation_messages(self):
        messages = self.assert_invalid(
            self.post({"name": "K", "species": "dog", "date_of_birth": str(days(1))}),
            "date_of_birth",
        )
        self.assertEqual(messages, ["Date of birth cannot be in the future."])
        messages = self.assert_invalid(
            self.post({"name": "K", "species": "dog", "weight_kg": 12.345}),
            "weight_kg",
        )
        self.assertEqual(
            messages, ["Ensure that there are no more than 2 decimal places."]
        )
        # Allergy item errors are keyed by index
        messages = self.assert_invalid(
            self.post({"name": "K", "species": "dog", "allergies": ["a" * 51]}),
            "allergies",
        )
        self.assertEqual(list(messages), ["0"])
        messages = self.assert_invalid(
            self.post({"name": "K", "species": "dog", "allergies": ["ok", ""]}),
            "allergies",
        )
        self.assertEqual(list(messages), ["1"])

    def test_microchip_must_be_exactly_15_digits(self):
        for value in ["1" * 14, "1" * 16, "abcdefghijklmno"]:
            with self.subTest(value):
                body = {"name": "Kopi", "species": "dog", "microchip_no": value}
                messages = self.assert_invalid(self.post(body), "microchip_no")
                self.assertEqual(messages, MICROCHIP_MESSAGE)

    def test_date_of_birth_today_is_accepted(self):
        response = self.post(
            {"name": "K", "species": "cat", "date_of_birth": str(TODAY)}
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_blank_or_null_microchip_is_stored_blank_and_shown_null(self):
        for value in ["", None]:
            with self.subTest(value):
                body = {"name": "Kopi", "species": "dog", "microchip_no": value}
                response = self.post(body)
                self.assertEqual(response.status_code, 201, response.content)
                self.assertIsNone(response.json()["microchip_no"])
                pet = Pet.objects.get(pk=response.json()["id"])
                self.assertEqual(pet.microchip_no, "")

    def test_allergies_are_trimmed_and_deduplicated(self):
        body = {
            "name": "Kopi",
            "species": "dog",
            "allergies": [" Chicken ", "chicken", "Beef"],
        }
        response = self.post(body)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["allergies"], ["Chicken", "Beef"])
        pet = Pet.objects.get(pk=response.json()["id"])
        self.assertEqual(pet.allergies, ["Chicken", "Beef"])

    def test_integrity_error_is_a_clean_conflict(self):
        failure = IntegrityError("Failing row contains (secret)")
        with mock.patch.object(Pet, "save", side_effect=failure):
            response = self.post({"name": "Kopi", "species": "dog"})
        messages = self.assert_invalid(response, "non_field_errors")
        self.assertEqual(messages, [CONFLICT_MESSAGE])
        self.assertNotIn(b"secret", response.content)
        self.assertNotIn(b"Failing row", response.content)


class PetDetailTests(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(
            self.alice, breed="Singapore Special", diet_notes="Salmon"
        )
        self.bobs = self.make_pet(self.bob, name="Sesame", species=Pet.RABBIT)

    def test_get_own_pet(self):
        response = self.client.get(detail(self.pet))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.pet.pk))
        self.assertEqual(response.json()["breed"], "Singapore Special")

    def test_other_owner_or_malformed_id_is_404(self):
        for url in [detail(self.bobs), detail("not-a-uuid"), detail(uuid.uuid4())]:
            with self.subTest(url):
                response = self.client.get(url)
                self.assert_error(response, 404, "not_found")
                self.assertEqual(
                    response.json()["error"],
                    {"code": "not_found", "message": "Not found.", "details": {}},
                )

    def test_patch_changes_only_the_given_field(self):
        response = self.client.patch(detail(self.pet), {"name": "Kopi II"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["name"], "Kopi II")
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.name, "Kopi II")
        self.assertEqual(self.pet.breed, "Singapore Special")
        self.assertEqual(self.pet.diet_notes, "Salmon")
        self.assertEqual(self.pet.species, Pet.DOG)

    def test_patch_validates(self):
        response = self.client.patch(detail(self.pet), {"name": ""}, format="json")
        self.assert_invalid(response, "name")
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.name, "Kopi")

    def test_patch_other_owner_is_404_and_unchanged(self):
        response = self.client.patch(detail(self.bobs), {"name": "Hacked"})
        self.assert_error(response, 404, "not_found")
        self.bobs.refresh_from_db()
        self.assertEqual(self.bobs.name, "Sesame")

    def test_put_is_not_allowed(self):
        body = {"name": "Kopi", "species": "cat"}
        response = self.client.put(detail(self.pet), body, format="json")
        self.assert_error(response, 405, "method_not_allowed")
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.species, Pet.DOG)

    def test_photo_version_is_the_key_stem(self):
        version = str(uuid.uuid4())
        Pet.objects.filter(pk=self.pet.pk).update(
            photo_key=f"pets/{self.pet.pk}/photos/{version}.jpg",
            photo_content_type="image/jpeg",
        )
        response = self.client.get(detail(self.pet))
        self.assertEqual(response.json()["photo_version"], version)
        self.assertEqual(
            response.json()["photo_url"],
            f"https://files.test/get/pets/{self.pet.pk}/photos/{version}.jpg",
        )


class PetDeleteTests(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(
            self.alice,
            photo_key=f"pets/{uuid.uuid4()}/photos/{uuid.uuid4()}.jpg",
            photo_content_type="image/jpeg",
            pending_photo_key=f"pets/{uuid.uuid4()}/photos/{uuid.uuid4()}.png",
            pending_photo_content_type="image/png",
            pending_photo_size_bytes=10,
        )
        record = self.make_record(self.pet)
        self.ready = self.make_document(self.pet, health_record=record)
        self.pending = self.make_document(self.pet, status=PetDocument.PENDING)
        self.make_reminder(self.pet, health_record=record)

    def test_delete_cascades_and_removes_files_after_commit(self):
        other = self.make_pet(self.alice, name="Mochi")
        self.make_reminder(other)

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.delete(detail(self.pet))

        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(callbacks), 1)
        self.assertFalse(Pet.objects.filter(pk=self.pet.pk).exists())
        self.assertFalse(HealthRecord.objects.exists())
        self.assertFalse(PetDocument.objects.exists())
        self.assertEqual(
            list(Reminder.objects.values_list("pet", flat=True)), [other.pk]
        )
        self.assertCountEqual(
            self.deleted_keys(),
            [
                self.pet.photo_key,
                self.pet.pending_photo_key,
                self.ready.file_key,
                self.pending.file_key,
            ],
        )

    def test_delete_succeeds_when_storage_is_unavailable(self):
        self.delete.side_effect = StorageUnavailable
        with (
            self.assertLogs("api.storage", "WARNING") as logs,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.delete(detail(self.pet))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Pet.objects.filter(pk=self.pet.pk).exists())
        self.assertEqual(self.delete.call_count, 4)
        # Logged by exception class only, never the key
        self.assertTrue(
            all(
                "Pet file cleanup failed: StorageUnavailable" in line
                for line in logs.output
            )
        )
        self.assertNotIn(self.ready.file_key, "\n".join(logs.output))

    def test_delete_other_owner_is_404(self):
        bobs = self.make_pet(self.bob, name="Sesame")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(detail(bobs))
        self.assert_error(response, 404, "not_found")
        self.assertTrue(Pet.objects.filter(pk=bobs.pk).exists())
        self.delete.assert_not_called()


class StalePendingPurgeTests(PetsAPITestCase):
    """Abandoned uploads are purged when the owner requests a new upload."""

    def setUp(self):
        super().setUp()
        self.two_hours_ago = timezone.now() - timedelta(hours=2)
        self.pet = self.make_pet(self.alice)

    def pending_photo(self, owner, name, requested_at):
        return self.make_pet(
            owner,
            name=name,
            pending_photo_key=f"pets/{uuid.uuid4()}/photos/{uuid.uuid4()}.jpg",
            pending_photo_content_type="image/jpeg",
            pending_photo_size_bytes=10,
            pending_photo_requested_at=requested_at,
        )

    def pending_document(self, pet, age):
        doc = self.make_document(pet, status=PetDocument.PENDING)
        PetDocument.objects.filter(pk=doc.pk).update(created_at=timezone.now() - age)
        return doc

    def request_photo_upload(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{detail(self.pet)}photo-upload/",
                {"content_type": "image/jpeg", "size_bytes": 1000},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)

    def test_photo_upload_request_purges_stale_documents(self):
        stale = self.pending_document(self.pet, timedelta(hours=2))
        fresh = self.pending_document(self.pet, timedelta(minutes=10))
        ready = self.make_document(self.pet)
        PetDocument.objects.filter(pk=ready.pk).update(created_at=self.two_hours_ago)

        self.request_photo_upload()

        self.assertFalse(PetDocument.objects.filter(pk=stale.pk).exists())
        self.assertTrue(PetDocument.objects.filter(pk=fresh.pk).exists())
        self.assertTrue(PetDocument.objects.filter(pk=ready.pk).exists())
        self.assertEqual(self.deleted_keys(), [stale.file_key])

    def test_photo_upload_request_purges_stale_pending_photos(self):
        stale = self.pending_photo(self.alice, "Mochi", self.two_hours_ago)
        fresh = self.pending_photo(
            self.alice, "Nemo", timezone.now() - timedelta(minutes=10)
        )

        self.request_photo_upload()

        stale_key = stale.pending_photo_key
        stale.refresh_from_db()
        self.assertEqual(
            (
                stale.pending_photo_key,
                stale.pending_photo_content_type,
                stale.pending_photo_size_bytes,
                stale.pending_photo_requested_at,
            ),
            ("", "", None, None),
        )
        fresh_key = fresh.pending_photo_key
        fresh.refresh_from_db()
        self.assertEqual(fresh.pending_photo_key, fresh_key)
        self.assertEqual(self.deleted_keys(), [stale_key])

    def test_other_owners_stale_uploads_are_untouched(self):
        bobs = self.pending_photo(self.bob, "Sesame", self.two_hours_ago)
        bobs_doc = self.pending_document(bobs, timedelta(hours=2))

        self.request_photo_upload()

        self.assertTrue(PetDocument.objects.filter(pk=bobs_doc.pk).exists())
        key = bobs.pending_photo_key
        bobs.refresh_from_db()
        self.assertEqual(bobs.pending_photo_key, key)
        self.assertEqual(bobs.pending_photo_requested_at, self.two_hours_ago)
        self.delete.assert_not_called()
