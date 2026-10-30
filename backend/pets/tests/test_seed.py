import os
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from pets.models import HealthRecord, Pet, PetDocument, Reminder
from pets.reminders import due_at_for_date

from .base import TODAY, days


class SeedPetsTests(TestCase):
    def setUp(self):
        patcher = mock.patch("pets.reminders.today_sgt", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)
        # The command refuses to run in Lambda; keep the shell from deciding that
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)

    def seed(self, *args):
        out = StringIO()
        call_command("seed_pets", *args, stdout=out)
        return out.getvalue()

    def counts(self):
        return (
            Pet.objects.count(),
            HealthRecord.objects.count(),
            Reminder.objects.count(),
        )

    def test_seeds_the_dev_users(self):
        output = self.seed()

        users = get_user_model().objects
        subs = sorted(users.values_list("cognito_sub", flat=True))
        self.assertEqual(subs, ["dev:alice", "dev:bob", "dev:mira"])
        self.assertEqual(self.counts(), (5, 5, 5))
        self.assertFalse(PetDocument.objects.exists())
        self.assertIn(
            "Seeded 5 pets, 5 records and 5 reminders for dev-alice, dev-bob, dev-mira.",
            output,
        )
        alice = users.get(cognito_sub="dev:alice")
        pets = {p.name: p for p in Pet.objects.filter(owner=alice)}
        self.assertEqual(sorted(pets), ["Kopi", "Mochi"])
        self.assertEqual(pets["Kopi"].microchip_no, "702000000000011")
        self.assertEqual(pets["Kopi"].allergies, ["Chicken"])
        overdue = Reminder.objects.get(pet=pets["Kopi"], title="Deworming tablet")
        self.assertEqual(overdue.due_at, due_at_for_date(days(-5)))
        self.assertEqual(overdue.health_record.name, "Deworming tablet")
        mira = users.get(cognito_sub="dev:mira")
        self.assertEqual(
            list(Pet.objects.filter(owner=mira).values_list("name", flat=True)),
            ["Biscuit"],
        )

    def test_rerun_is_idempotent_and_keeps_other_rows(self):
        self.seed()
        alice = get_user_model().objects.get(cognito_sub="dev:alice")
        extra = Pet.objects.create(owner=alice, name="Tofu", species=Pet.RABBIT)
        nail_trim = Reminder.objects.get(pet__owner=alice, title="Nail trim")
        nail_trim.done = False
        nail_trim.save(update_fields=["done"])

        self.seed()

        self.assertEqual(self.counts(), (6, 5, 5))
        self.assertTrue(Pet.objects.filter(pk=extra.pk).exists())
        nail_trim.refresh_from_db()
        self.assertTrue(nail_trim.done)  # reset to the template

    def test_rerun_ignores_same_named_rows_the_user_created(self):
        self.seed()
        alice = get_user_model().objects.get(cognito_sub="dev:alice")
        kopi = Pet.objects.get(owner=alice, name="Kopi")
        mochi = Pet.objects.get(owner=alice, name="Mochi")
        own_pet = Pet.objects.create(
            owner=alice, name="Kopi", species=Pet.CAT, breed="Mine"
        )
        own_record = HealthRecord.objects.create(
            pet=kopi,
            record_type=HealthRecord.DEWORMING,
            name="Deworming tablet",
            date=days(0),
            notes="Next monthly dose",
        )
        own_reminder = Reminder.objects.create(
            pet=mochi, title="Nail trim", due_at=due_at_for_date(days(10))
        )
        before = [
            (Pet, own_pet.pk, {"species": Pet.CAT, "breed": "Mine"}),
            (
                HealthRecord,
                own_record.pk,
                {"date": days(0), "notes": "Next monthly dose"},
            ),
            (Reminder, own_reminder.pk, {"due_at": due_at_for_date(days(10))}),
        ]

        self.seed()  # used to raise MultipleObjectsReturned

        self.assertEqual(self.counts(), (6, 6, 6))
        for model, pk, fields in before:
            row = model.objects.get(pk=pk)
            for field, value in fields.items():
                with self.subTest(model=model.__name__, field=field):
                    self.assertEqual(getattr(row, field), value)
        self.assertIs(Reminder.objects.get(pk=own_reminder.pk).done, False)

    def test_user_target_keeps_their_own_same_named_pet(self):
        carol = get_user_model().objects.create_user(username="carol")
        own_kopi = Pet.objects.create(
            owner=carol,
            name="Kopi",
            species=Pet.DOG,
            breed="Shiba Inu",
            microchip_no="123456789012345",
            allergies=["Beef"],
        )

        self.seed("--user", "carol", "--skip-dev-users")

        own_kopi.refresh_from_db()
        self.assertEqual(own_kopi.breed, "Shiba Inu")
        self.assertEqual(own_kopi.microchip_no, "123456789012345")
        self.assertEqual(own_kopi.allergies, ["Beef"])
        kopis = Pet.objects.filter(owner=carol, name="Kopi").exclude(pk=own_kopi.pk)
        self.assertEqual(kopis.get().breed, "Singapore Special")
        self.assertEqual(self.counts(), (3, 3, 3))
        self.assertFalse(own_kopi.records.exists())

    def test_seeds_an_existing_user_with_alices_pets(self):
        carol = get_user_model().objects.create_user(
            username="carol", email="Carol@Example.test"
        )

        self.seed("--user", "carol", "--skip-dev-users")

        self.assertEqual(
            sorted(Pet.objects.filter(owner=carol).values_list("name", flat=True)),
            ["Kopi", "Mochi"],
        )
        self.assertEqual(self.counts(), (2, 3, 3))
        self.assertFalse(
            get_user_model().objects.filter(cognito_sub__startswith="dev:").exists()
        )

        # Email matches case-insensitively, and dev users can be seeded alongside
        self.seed("--user", "carol@example.test")
        self.assertEqual(self.counts(), (7, 8, 8))

    def test_unknown_user_is_an_error(self):
        with self.assertRaisesMessage(CommandError, "No unique user matches 'nobody'."):
            self.seed("--user", "nobody")
        self.assertFalse(Pet.objects.exists())

    def test_refuses_to_run_in_lambda(self):
        with (
            mock.patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "api"}),
            self.assertRaisesMessage(
                CommandError, "seed_pets is for local development only."
            ),
        ):
            self.seed()
        self.assertFalse(get_user_model().objects.exists())
