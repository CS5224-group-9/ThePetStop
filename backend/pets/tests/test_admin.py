import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from pets.models import HealthRecord, Pet, PetDocument, Reminder

from .base import days


class PetsAdminTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        admin = users.create_superuser(username="admin", email="admin@example.test")
        owner = users.create_user(username="alice", email="alice@example.test")
        pet = Pet.objects.create(owner=owner, name="Kopi", species=Pet.DOG)
        record = HealthRecord.objects.create(
            pet=pet,
            record_type=HealthRecord.CHECKUP,
            name="Annual check",
            date=days(-1),
        )
        PetDocument.objects.create(
            pet=pet,
            health_record=record,
            title="Blood test",
            file_key=f"pets/{pet.pk}/documents/{uuid.uuid4()}.pdf",
            content_type=PetDocument.PDF,
            size_bytes=3,
            status=PetDocument.READY,
            uploaded_at=timezone.now(),
        )
        Reminder.objects.create(pet=pet, title="Booster", due_at=timezone.now())
        self.client.force_login(admin)

    def test_changelists_load(self):
        rows = {
            "pet": "Kopi",
            "healthrecord": "Annual check",
            "petdocument": "Blood test",
            "reminder": "Booster",
        }
        for model, text in rows.items():
            with self.subTest(model):
                response = self.client.get(reverse(f"admin:pets_{model}_changelist"))
                self.assertContains(response, text, status_code=200)

    def test_documents_cannot_be_added_in_the_admin(self):
        # Saving the add form used to fail with a NOT NULL size_bytes 500
        response = self.client.get(reverse("admin:pets_petdocument_add"))
        self.assertEqual(response.status_code, 403)
