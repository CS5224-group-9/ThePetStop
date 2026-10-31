from api.storage import StoredObject
from pets.models import PetDocument

from .base import API, PetsAPITestCase, days


def stored_object(key):
    """What storage holds after a correct PUT of the uploads requested below."""
    if "/photos/" in key:
        return StoredObject(1000, "image/jpeg")
    return StoredObject(3, "application/pdf")


class NoStoreTests(PetsAPITestCase):
    def test_every_operation_is_no_store(self):
        self.head.side_effect = stored_object
        pet = self.make_pet(self.alice)
        doomed_pet = self.make_pet(self.alice, name="Mochi")
        record = self.make_record(pet)
        doomed_record = self.make_record(pet, name="Old check-up")
        ready = self.make_document(pet)
        pending = self.make_document(pet, status=PetDocument.PENDING)
        reminder = self.make_reminder(pet)
        doomed_reminder = self.make_reminder(pet, title="Old")
        bobs = self.make_pet(self.bob, name="Sesame")

        p = f"{API}pets/{pet.pk}/"
        reminder_body = {
            "pet": str(pet.pk),
            "title": "Booster",
            "due_at": "2026-11-05T09:00:00+08:00",
        }
        operations = [
            # A4 rows 1-24, in order
            ("get", f"{API}pets/", None, 200),
            ("post", f"{API}pets/", {"name": "Nemo", "species": "fish"}, 201),
            ("get", p, None, 200),
            ("patch", p, {"name": "Kopi II"}, 200),
            ("delete", f"{API}pets/{doomed_pet.pk}/", None, 204),
            (
                "post",
                f"{p}photo-upload/",
                {"content_type": "image/jpeg", "size_bytes": 1000},
                200,
            ),
            ("post", f"{p}photo-upload/complete/", None, 200),
            ("delete", f"{p}photo/", None, 204),
            ("get", f"{p}records/", None, 200),
            (
                "post",
                f"{p}records/",
                {"name": "Rabies", "record_type": "vaccination", "date": str(days(-1))},
                201,
            ),
            ("get", f"{p}records/{record.pk}/", None, 200),
            ("patch", f"{p}records/{record.pk}/", {"notes": "Fine"}, 200),
            ("delete", f"{p}records/{doomed_record.pk}/", None, 204),
            ("get", f"{p}documents/", None, 200),
            (
                "post",
                f"{p}documents/",
                {"title": "Scan", "content_type": "application/pdf", "size_bytes": 3},
                201,
            ),
            ("get", f"{p}documents/{ready.pk}/", None, 200),
            ("patch", f"{p}documents/{ready.pk}/", {"title": "Blood test"}, 200),
            ("delete", f"{p}documents/{ready.pk}/", None, 204),
            ("post", f"{p}documents/{pending.pk}/complete/", None, 200),
            ("get", f"{API}reminders/", None, 200),
            ("post", f"{API}reminders/", reminder_body, 201),
            ("get", f"{API}reminders/{reminder.pk}/", None, 200),
            ("patch", f"{API}reminders/{reminder.pk}/", {"done": True}, 200),
            ("delete", f"{API}reminders/{doomed_reminder.pk}/", None, 204),
            # Errors too
            ("get", f"{API}pets/{bobs.pk}/", None, 404),
            ("put", p, {"name": "x", "species": "dog"}, 405),
            ("post", f"{p}records/", {"name": ""}, 400),
            ("post", f"{p}photo-upload/complete/", None, 409),
        ]
        self.assertEqual(len(operations) - 4, 24)

        for method, url, body, expected in operations:
            with self.subTest(f"{method.upper()} {url}"):
                response = getattr(self.client, method)(url, body)
                self.assertEqual(response.status_code, expected, response.content)
                self.assertEqual(response["Cache-Control"], "no-store")

        self.client.force_authenticate(None)
        response = self.client.get(f"{API}pets/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Cache-Control"], "no-store")
