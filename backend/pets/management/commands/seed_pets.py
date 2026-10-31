"""Idempotent demo pets, care records and reminders for local development.

All data is fictional. Seeded rows have fixed ids derived from the owner and the
template names, so re-running finds exactly those rows, resets them to the
template (dates move with today and `done` resets) and never touches other rows,
even ones with the same names. No documents or photos are seeded.
"""

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from api.authentication import get_dev_user
from pets import reminders
from pets.models import HealthRecord, Pet, Reminder

CLINIC = "Sample Veterinary Clinic"
DEV_HANDLES = ["alice", "bob", "mira"]
# Namespace of the seeded rows' uuid5 ids
SEED_NAMESPACE = uuid.UUID("1c091fcf-b1c9-4a1d-93b0-d7fb88460c44")

# Per owner template: pets, each with records (type, name, date offset, next_due
# offset) and reminders (title, due offset, done, linked record name). Offsets
# are days from today in Singapore.
TEMPLATES = {
    "alice": [
        {
            "name": "Kopi",
            "species": Pet.DOG,
            "breed": "Singapore Special",
            "sex": Pet.MALE,
            "date_of_birth": date(2022, 4, 12),
            "microchip_no": "702000000000011",
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
            "species": Pet.CAT,
            "breed": "Domestic Shorthair",
            "sex": Pet.FEMALE,
            "date_of_birth": date(2023, 8, 20),
            "microchip_no": "",
            "allergies": [],
            "diet_notes": "Indoor cat food",
            "weight_kg": Decimal("4.10"),
            "records": [
                (HealthRecord.CHECKUP, "Annual health check", -200, 165),
            ],
            "reminders": [
                ("Nail trim", -20, True, None),
            ],
        },
    ],
    "bob": [
        {
            "name": "Sesame",
            "species": Pet.RABBIT,
            "breed": "Holland Lop",
            "sex": Pet.FEMALE,
            "date_of_birth": date(2024, 2, 15),
            "microchip_no": "",
            "allergies": [],
            "diet_notes": "Timothy hay and leafy greens",
            "weight_kg": Decimal("1.80"),
            "records": [
                (HealthRecord.GROOMING, "Nail trim", -30, 30),
            ],
            "reminders": [
                ("Nail trim", 30, False, "Nail trim"),
            ],
        },
        {
            "name": "Nemo",
            "species": Pet.FISH,
            "breed": "Clownfish",
            "sex": Pet.UNKNOWN,
            "date_of_birth": None,
            "microchip_no": "",
            "allergies": [],
            "diet_notes": "Marine flakes",
            "weight_kg": None,
            "records": [],
            "reminders": [
                ("Water change", 6, False, None),
            ],
        },
    ],
    "mira": [
        {
            "name": "Biscuit",
            "species": Pet.DOG,
            "breed": "Golden Retriever",
            "sex": Pet.MALE,
            "date_of_birth": date(2021, 1, 5),
            "microchip_no": "",
            "allergies": [],
            "diet_notes": "Large-breed kibble",
            "weight_kg": Decimal("30.50"),
            "records": [
                (HealthRecord.VACCINATION, "Rabies vaccination", -100, 265),
            ],
            "reminders": [],
        },
    ],
}

PET_FIELDS = [
    "species",
    "breed",
    "sex",
    "date_of_birth",
    "microchip_no",
    "allergies",
    "diet_notes",
    "weight_kg",
]


def seed_id(*parts) -> uuid.UUID:
    """The fixed id of a seeded row, e.g. seed_id("pet", user.pk, "Kopi")."""
    return uuid.uuid5(SEED_NAMESPACE, "/".join(str(part) for part in parts))


class Command(BaseCommand):
    help = (
        "Create demo pets, records and reminders for the local dev users (alice, "
        "bob, mira) and optionally for existing users. Safe to run repeatedly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            action="append",
            default=[],
            metavar="USERNAME_OR_EMAIL",
            help="Also seed this existing user (exact username or case-insensitive "
            "email) with alice's pets. Repeatable.",
        )
        parser.add_argument(
            "--skip-dev-users",
            action="store_true",
            help="Do not create or seed the dev users alice, bob and mira.",
        )

    def handle(self, *args, **options):
        if "AWS_LAMBDA_FUNCTION_NAME" in os.environ:
            raise CommandError("seed_pets is for local development only.")

        with transaction.atomic():
            targets = []  # (user, template name), in order, without repeats
            if not options["skip_dev_users"]:
                targets += [(get_dev_user(handle), handle) for handle in DEV_HANDLES]
            targets += [(self.find_user(value), "alice") for value in options["user"]]
            if not targets:
                raise CommandError(
                    "Nothing to seed: pass --user or leave out --skip-dev-users."
                )

            today = reminders.today_sgt()
            counts = {"pets": 0, "records": 0, "reminders": 0}
            seen = set()
            usernames = []
            for user, template in targets:
                if (user.pk, template) in seen:
                    continue
                seen.add((user.pk, template))
                if user.username not in usernames:
                    usernames.append(user.username)
                for pet_template in TEMPLATES[template]:
                    self.seed_pet(user, pet_template, today, counts)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {counts['pets']} pets, {counts['records']} records and "
                f"{counts['reminders']} reminders for {', '.join(usernames)}."
            )
        )

    @staticmethod
    def find_user(value):
        value = value.strip()
        matches = (
            list(
                get_user_model()
                .objects.filter(Q(username=value) | Q(email__iexact=value))
                .distinct()[:2]
            )
            if value
            else []
        )
        if len(matches) != 1:
            raise CommandError(f"No unique user matches {value!r}.")
        return matches[0]

    @staticmethod
    def seed_pet(user, template, today, counts):
        def day(offset):
            return today + timedelta(days=offset)

        pet_name = template["name"]
        pet, _ = Pet.objects.update_or_create(
            id=seed_id("pet", user.pk, pet_name),
            defaults={
                "owner": user,
                "name": pet_name,
                **{field: template[field] for field in PET_FIELDS},
            },
        )
        counts["pets"] += 1

        records = {}
        for record_type, name, date_offset, next_due_offset in template["records"]:
            record, _ = HealthRecord.objects.update_or_create(
                id=seed_id("record", user.pk, pet_name, record_type, name),
                defaults={
                    "pet": pet,
                    "record_type": record_type,
                    "name": name,
                    "date": day(date_offset),
                    "next_due": day(next_due_offset),
                    "clinic": CLINIC,
                    "notes": "",
                },
            )
            records[name] = record
            counts["records"] += 1

        for title, due_offset, done, record_name in template["reminders"]:
            Reminder.objects.update_or_create(
                id=seed_id("reminder", user.pk, pet_name, title),
                defaults={
                    "pet": pet,
                    "title": title,
                    "due_at": reminders.due_at_for_date(day(due_offset)),
                    "done": done,
                    "health_record": records[record_name] if record_name else None,
                },
            )
            counts["reminders"] += 1
