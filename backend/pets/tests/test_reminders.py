import uuid
from datetime import date

from pets.models import Reminder
from pets.reminders import due_at_for_date

from .base import API, PetsAPITestCase, does_not_exist

REMINDERS = f"{API}reminders/"


def reminder_url(reminder) -> str:
    return f"{REMINDERS}{getattr(reminder, 'pk', reminder)}/"


class ReminderListTests(PetsAPITestCase):
    """Today is patched to 2026-10-30 (Asia/Singapore)."""

    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(self.alice)
        self.other_pet = self.make_pet(self.alice, name="Mochi")
        self.bobs = self.make_pet(self.bob, name="Sesame")
        cases = [
            ("Upcoming", date(2026, 11, 7), False, self.pet),
            ("Due today", date(2026, 10, 30), False, self.pet),
            ("Overdue", date(2026, 10, 29), False, self.pet),
            ("Due in a week", date(2026, 11, 6), False, self.other_pet),
            ("Done long ago", date(2026, 9, 1), True, self.other_pet),
        ]
        for title, day, done, pet in cases:
            self.make_reminder(pet, title=title, due_at=due_at_for_date(day), done=done)
        self.make_reminder(
            self.bobs, title="Bob's", due_at=due_at_for_date(date(2026, 10, 1))
        )

    def titles(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        return [r["title"] for r in response.json()["results"]]

    def test_lists_all_own_reminders_by_due_date_with_flags(self):
        response = self.client.get(REMINDERS)

        self.assertEqual(response.status_code, 200)
        flags = [
            (r["title"], r["done"], r["is_overdue"], r["is_due_soon"])
            for r in response.json()["results"]
        ]
        self.assertEqual(
            flags,
            [
                ("Done long ago", True, False, False),
                ("Overdue", False, True, False),
                ("Due today", False, False, True),
                ("Due in a week", False, False, True),
                ("Upcoming", False, False, False),
            ],
        )
        first = response.json()["results"][0]
        self.assertEqual(
            list(first),
            [
                "id",
                "pet",
                "health_record",
                "title",
                "due_at",
                "done",
                "is_overdue",
                "is_due_soon",
                "created_at",
                "updated_at",
            ],
        )
        self.assertEqual(first["due_at"], "2026-09-01T09:00:00+08:00")
        for row in response.json()["results"]:
            self.assertTrue(row["due_at"].endswith("+08:00"), row["due_at"])

    def test_pet_filter(self):
        self.assertEqual(
            self.titles(self.client.get(REMINDERS, {"pet": str(self.pet.pk)})),
            ["Overdue", "Due today", "Upcoming"],
        )
        # Another owner's pet simply matches nothing
        self.assertEqual(
            self.titles(self.client.get(REMINDERS, {"pet": str(self.bobs.pk)})), []
        )
        self.assertEqual(
            self.titles(self.client.get(REMINDERS, {"pet": str(uuid.uuid4())})), []
        )
        self.assert_invalid(self.client.get(REMINDERS, {"pet": "abc"}), "pet")

    def test_done_filter(self):
        self.assertEqual(
            self.titles(self.client.get(REMINDERS, {"done": "true"})), ["Done long ago"]
        )
        self.assertEqual(
            self.titles(self.client.get(REMINDERS, {"done": "false"})),
            ["Overdue", "Due today", "Due in a week", "Upcoming"],
        )
        self.assert_invalid(self.client.get(REMINDERS, {"done": "maybe"}), "done")

    def test_anonymous_gets_401(self):
        self.client.force_authenticate(None)
        self.assert_error(self.client.get(REMINDERS), 401, "not_authenticated")

    def test_merchant_without_pets_gets_an_empty_list(self):
        self.client.force_authenticate(self.merchant)
        response = self.client.get(REMINDERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(response.json()["results"], [])


class ReminderCreateTests(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(self.alice)
        self.other_pet = self.make_pet(self.alice, name="Mochi")
        self.bobs = self.make_pet(self.bob, name="Sesame")

    def post(self, **overrides):
        body = {
            "pet": str(self.pet.pk),
            "title": "Booster",
            "due_at": "2026-11-05T09:00:00+08:00",
            **overrides,
        }
        return self.client.post(REMINDERS, body)

    def test_create_for_own_pet(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["pet"], str(self.pet.pk))
        self.assertIsNone(body["health_record"])
        self.assertIs(body["done"], False)
        self.assertIs(body["is_due_soon"], True)
        self.assertIs(body["is_overdue"], False)
        self.assertEqual(Reminder.objects.get(pk=body["id"]).pet, self.pet)

    def test_due_at_is_rendered_in_singapore_time(self):
        response = self.post(due_at="2026-11-05T01:00:00Z")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["due_at"], "2026-11-05T09:00:00+08:00")

    def test_foreign_or_unknown_pet_looks_the_same(self):
        for pk in [self.bobs.pk, uuid.uuid4()]:
            with self.subTest(pk=pk):
                messages = self.assert_invalid(self.post(pet=str(pk)), "pet")
                self.assertEqual(messages, [does_not_exist(pk)])
        self.assertFalse(Reminder.objects.exists())

    def test_health_record_must_belong_to_the_same_pet(self):
        record = self.make_record(self.pet)
        response = self.post(health_record=str(record.pk))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["health_record"], str(record.pk))

        other_record = self.make_record(self.other_pet)
        bobs_record = self.make_record(self.bobs)
        for record in [other_record, bobs_record]:
            with self.subTest(record=record.pet.name):
                response = self.post(health_record=str(record.pk))
                messages = self.assert_invalid(response, "health_record")
                self.assertEqual(messages, [does_not_exist(record.pk)])
        self.assertEqual(Reminder.objects.count(), 1)

    def test_validation_errors(self):
        cases = {
            "blank title": ({"title": ""}, "title"),
            "151-char title": ({"title": "t" * 151}, "title"),
            "bad due_at": ({"due_at": "soon"}, "due_at"),
        }
        for name, (overrides, field) in cases.items():
            with self.subTest(name):
                self.assert_invalid(self.post(**overrides), field)
        body = {"pet": str(self.pet.pk), "title": "Booster"}
        self.assert_invalid(self.client.post(REMINDERS, body), "due_at")
        self.assert_invalid(
            self.client.post(REMINDERS, {"title": "x", "due_at": "2026-11-05"}), "pet"
        )
        self.assertFalse(Reminder.objects.exists())

    def test_naive_due_at_out_of_range_is_invalid(self):
        # Before about 07:00 SGT on 0001-01-01 the UTC conversion underflows (was a 500)
        messages = self.assert_invalid(
            self.post(due_at="0001-01-01T05:00:00"), "due_at"
        )
        self.assertEqual(messages, ["Datetime value out of range."])
        self.assertFalse(Reminder.objects.exists())


class ReminderDetailTests(PetsAPITestCase):
    def setUp(self):
        super().setUp()
        self.pet = self.make_pet(self.alice)
        self.other_pet = self.make_pet(self.alice, name="Mochi")
        self.bobs = self.make_pet(self.bob, name="Sesame")
        self.reminder = self.make_reminder(
            self.pet, title="Deworming", due_at=due_at_for_date(date(2026, 10, 25))
        )
        self.url = reminder_url(self.reminder)
        self.bobs_reminder = self.make_reminder(self.bobs, title="Nail trim")

    def test_get_own_reminder(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["is_overdue"], True)

    def test_mark_done_clears_overdue(self):
        response = self.client.patch(self.url, {"done": True})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(
            (body["done"], body["is_overdue"], body["is_due_soon"]),
            (True, False, False),
        )
        response = self.client.patch(self.url, {"done": False})
        self.assertIs(response.json()["is_overdue"], True)

    def test_reschedule_changes_flags(self):
        response = self.client.patch(self.url, {"due_at": "2026-11-02T09:00:00+08:00"})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["due_at"], "2026-11-02T09:00:00+08:00")
        self.assertEqual((body["is_overdue"], body["is_due_soon"]), (False, True))
        self.reminder.refresh_from_db()
        self.assertEqual(self.reminder.due_at, due_at_for_date(date(2026, 11, 2)))

    def test_rename(self):
        response = self.client.patch(self.url, {"title": "Deworming tablet"})
        self.assertEqual(response.status_code, 200, response.content)
        self.reminder.refresh_from_db()
        self.assertEqual(self.reminder.title, "Deworming tablet")

    def test_cannot_move_to_another_pet(self):
        response = self.client.patch(self.url, {"pet": str(self.other_pet.pk)})
        messages = self.assert_invalid(response, "pet")
        self.assertEqual(messages, ["A reminder cannot be moved to another pet."])
        # Bob's pet is not even a valid choice
        response = self.client.patch(self.url, {"pet": str(self.bobs.pk)})
        self.assertEqual(
            self.assert_invalid(response, "pet"), [does_not_exist(self.bobs.pk)]
        )
        self.reminder.refresh_from_db()
        self.assertEqual(self.reminder.pet, self.pet)

    def test_patch_health_record_of_another_pet(self):
        record = self.make_record(self.pet)
        response = self.client.patch(self.url, {"health_record": str(record.pk)})
        self.assertEqual(response.status_code, 200, response.content)

        other_record = self.make_record(self.other_pet)
        response = self.client.patch(self.url, {"health_record": str(other_record.pk)})
        messages = self.assert_invalid(response, "health_record")
        self.assertEqual(messages, [does_not_exist(other_record.pk)])
        self.reminder.refresh_from_db()
        self.assertEqual(self.reminder.health_record, record)

        response = self.client.patch(self.url, {"health_record": None})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["health_record"])

    def test_other_owner_or_malformed_id_is_404(self):
        for url in [reminder_url(self.bobs_reminder), reminder_url("nope")]:
            with self.subTest(url):
                self.assert_error(self.client.get(url), 404, "not_found")
                self.assert_error(
                    self.client.patch(url, {"done": True}), 404, "not_found"
                )
                self.assert_error(self.client.delete(url), 404, "not_found")
        self.bobs_reminder.refresh_from_db()
        self.assertFalse(self.bobs_reminder.done)

    def test_put_is_not_allowed(self):
        body = {
            "pet": str(self.pet.pk),
            "title": "x",
            "due_at": "2026-11-05T09:00:00+08:00",
        }
        self.assert_error(self.client.put(self.url, body), 405, "method_not_allowed")

    def test_delete(self):
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertFalse(Reminder.objects.filter(pk=self.reminder.pk).exists())
        self.assertTrue(Reminder.objects.filter(pk=self.bobs_reminder.pk).exists())
