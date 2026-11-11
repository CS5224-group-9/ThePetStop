from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APITestCase

from config.lambda_handler import manage
from marketplace.models import Merchant
from pets.models import Pet

OWNER_SUB = "a9fa555c-80b1-70ac-7b6f-7648de29953b"
MERCHANT_SUB = "994a35fc-a001-70cb-3d4f-3bbd6df0aa14"
ARGS = ["--owner-sub", OWNER_SUB, "--merchant-sub", MERCHANT_SUB]


class SeedDemoTests(APITestCase):
    def setUp(self):
        self.shop = Merchant.objects.create(
            name="Little Island Pets", slug="little-island-pets"
        )
        Merchant.objects.create(name="Harbour Paws Supply", slug="harbour-paws")

    def run_command(self, *args):
        call_command("seed_demo", *args, stdout=StringIO())

    def test_creates_users_pets_and_shop_owner_repeatably(self):
        for _ in range(2):
            self.run_command(*ARGS)

        users = get_user_model().objects
        owner = users.get(cognito_sub=OWNER_SUB)
        merchant = users.get(cognito_sub=MERCHANT_SUB)
        self.assertEqual(
            (owner.username, owner.email, owner.display_name),
            (OWNER_SUB, "jimmy@gmail.com", "Jimmy"),
        )
        self.assertEqual(
            (merchant.email, merchant.display_name),
            ("merchant@gmail.com", "Mr James"),
        )
        pets = Pet.objects.filter(owner=owner).order_by("name")
        self.assertEqual(
            [(p.name, p.species, p.breed) for p in pets],
            [("Kopi", "dog", "Singapore Special"), ("Mochi", "dog", "Shiba Inu")],
        )
        self.assertEqual(pets[0].records.count(), 2)
        self.assertEqual(pets[1].reminders.count(), 2)
        self.assertFalse(Pet.objects.filter(owner=merchant).exists())
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.owner, merchant)
        self.assertEqual(Merchant.objects.filter(owner=merchant).count(), 1)

    def test_reuses_user_created_at_first_sign_in(self):
        existing = get_user_model().objects.create_user(
            username=OWNER_SUB, cognito_sub=OWNER_SUB, email="old@example.test"
        )
        self.run_command("--owner-sub", OWNER_SUB)

        existing.refresh_from_db()
        self.assertEqual(existing.email, "jimmy@gmail.com")
        self.assertEqual(Pet.objects.filter(owner=existing).count(), 2)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_seeded_merchant_can_list_shop_orders(self):
        self.run_command("--merchant-sub", MERCHANT_SUB)
        merchant = get_user_model().objects.get(cognito_sub=MERCHANT_SUB)
        self.client.force_authenticate(merchant)

        self.assertEqual(self.client.get("/api/v1/merchant/orders/").status_code, 200)
        me = self.client.get("/api/v1/me/").json()
        self.assertEqual(me["merchant"]["slug"], "little-island-pets")

    def test_does_not_take_another_users_shop(self):
        other = get_user_model().objects.create_user(username="other")
        self.shop.owner = other
        self.shop.save()

        with self.assertRaises(CommandError):
            self.run_command(*ARGS)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.owner, other)
        # One transaction: the owner half did not commit either
        self.assertFalse(get_user_model().objects.filter(cognito_sub=OWNER_SUB))

    def test_rejects_bad_arguments(self):
        for args in (
            [],
            ["--owner-sub", "dev:alice"],
            ["--owner-sub", OWNER_SUB, "--merchant-sub", OWNER_SUB],
        ):
            with self.subTest(args=args), self.assertRaises(CommandError):
                self.run_command(*args)
        self.assertFalse(get_user_model().objects.exists())

    def test_runs_in_manage_lambda(self):
        result = manage({"command": "seed_demo", "args": ARGS}, None)

        self.assertIn("Demo accounts ready", result["output"])
        self.assertEqual(Pet.objects.count(), 2)
