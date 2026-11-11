"""Idempotent demo accounts for the deployed site: pet owner Jimmy and merchant Mr James.

The Cognito users are created separately (see `backend/README.md`); pass their
`sub` values here. This creates or updates the matching Django users, so they work
before their first sign-in, seeds Jimmy's pets and gives Mr James a shop. All data
is fictional. Allowed in the `manage` Lambda, unlike the local-only seed commands.
"""

import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from marketplace.models import Merchant
from pets import reminders
from pets.management.commands.seed_pets import Command as SeedPets
from pets.models import HealthRecord, Pet

OWNER = {"email": "jimmy@gmail.com", "display_name": "Jimmy"}
MERCHANT = {
    "email": "merchant@gmail.com",
    "display_name": "Mr James",
    "shop": "little-island-pets",
}

# Same template format as seed_pets.TEMPLATES
OWNER_PETS = [
    {
        "name": "Kopi",
        "species": Pet.DOG,
        "breed": "Singapore Special",
        "sex": Pet.MALE,
        "date_of_birth": date(2022, 4, 12),
        "microchip_no": "702000000000021",
        "allergies": ["Chicken"],
        "diet_notes": "Salmon-based dry food",
        "weight_kg": Decimal("14.20"),
        "records": [
            (HealthRecord.VACCINATION, "DHPPiL booster", -330, 35),
            (HealthRecord.DEWORMING, "Deworming tablet", -95, -5),
        ],
        "reminders": [
            ("Deworming tablet", -5, False, "Deworming tablet"),
            ("Monthly flea & tick care", 3, False, None),
        ],
    },
    {
        "name": "Mochi",
        "species": Pet.DOG,
        "breed": "Shiba Inu",
        "sex": Pet.FEMALE,
        "date_of_birth": date(2023, 8, 20),
        "microchip_no": "702000000000022",
        "allergies": [],
        "diet_notes": "Grain-free kibble, twice a day",
        "weight_kg": Decimal("9.40"),
        "records": [
            (HealthRecord.CHECKUP, "Annual health check", -200, 165),
            (HealthRecord.GROOMING, "Coat brushing and nail trim", -25, 35),
        ],
        "reminders": [
            ("Nail trim", -20, True, None),
            ("Grooming appointment", 35, False, "Coat brushing and nail trim"),
        ],
    },
]


class Command(BaseCommand):
    help = (
        "Create or update the demo owner (Jimmy) and merchant (Mr James) for "
        "existing Cognito users, seed Jimmy's pets and assign the merchant's shop. "
        "Safe to run repeatedly."
    )

    def add_arguments(self, parser):
        parser.add_argument("--owner-sub", help=f"Cognito sub of {OWNER['email']}")
        parser.add_argument(
            "--merchant-sub", help=f"Cognito sub of {MERCHANT['email']}"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        owner_sub, merchant_sub = options["owner_sub"], options["merchant_sub"]
        if not (owner_sub or merchant_sub):
            raise CommandError("Pass --owner-sub, --merchant-sub or both.")
        if owner_sub and owner_sub == merchant_sub:
            raise CommandError("The owner and the merchant must be different users.")

        if owner_sub:
            owner = self.demo_user(owner_sub, OWNER)
            counts = {"pets": 0, "records": 0, "reminders": 0}
            today = reminders.today_sgt()
            for template in OWNER_PETS:
                SeedPets.seed_pet(owner, template, today, counts)
            self.stdout.write(
                f"{OWNER['display_name']}: {counts['pets']} pets, "
                f"{counts['records']} records, {counts['reminders']} reminders."
            )

        if merchant_sub:
            merchant = self.demo_user(merchant_sub, MERCHANT)
            shop = (
                Merchant.objects.select_for_update()
                .filter(slug=MERCHANT["shop"], active=True)
                .first()
            )
            if shop is None:
                raise CommandError("Shop not found. Run load_catalogue first.")
            if shop.owner_id not in (None, merchant.pk):
                raise CommandError(f"{shop.name} already belongs to another user.")
            shop.owner = merchant
            shop.save(update_fields=["owner"])
            self.stdout.write(f"{MERCHANT['display_name']} manages {shop.name}.")

        self.stdout.write(self.style.SUCCESS("Demo accounts ready."))

    @staticmethod
    def demo_user(sub, info):
        """The Django user for this Cognito sub, as CognitoAuthentication creates it."""
        try:
            sub = str(uuid.UUID(sub))
        except ValueError:
            raise CommandError(f"Not a Cognito sub: {sub!r}") from None
        user, _ = get_user_model().objects.get_or_create(
            cognito_sub=sub, defaults={"username": sub}
        )
        user.email = info["email"]
        user.display_name = info["display_name"]
        user.save(update_fields=["email", "display_name"])
        return user
