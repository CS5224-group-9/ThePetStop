"""Private pet profiles, care records, vet documents and in-app reminders.

Every row belongs to one owner through its pet; views filter every queryset by
the authenticated user. Files are stored as opaque keys (see pets/uploads.py),
never as URLs, and keys carry no names or other personal data.

No model creates reminders on its own: there are no signals and no save()
overrides. A vaccination's next_due only lets the client suggest one.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Pet(models.Model):
    DOG = "dog"
    CAT = "cat"
    RABBIT = "rabbit"
    BIRD = "bird"
    FISH = "fish"
    OTHER = "other"
    SPECIES_CHOICES = [
        (DOG, "Dog"),
        (CAT, "Cat"),
        (RABBIT, "Rabbit"),
        (BIRD, "Bird"),
        (FISH, "Fish"),
        (OTHER, "Other"),
    ]

    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"
    SEX_CHOICES = [(MALE, "Male"), (FEMALE, "Female"), (UNKNOWN, "Unknown")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pets"
    )
    name = models.CharField(max_length=50)
    species = models.CharField(max_length=10, choices=SPECIES_CHOICES)
    breed = models.CharField(max_length=80, blank=True, default="")
    sex = models.CharField(max_length=7, choices=SEX_CHOICES, default=UNKNOWN)
    date_of_birth = models.DateField(null=True, blank=True)
    # "" means not recorded; the API shows null
    microchip_no = models.CharField(max_length=15, blank=True, default="")
    allergies = models.JSONField(default=list, blank=True)
    diet_notes = models.CharField(max_length=500, blank=True, default="")
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    # The completed photo, shown through a presigned GET URL
    photo_key = models.CharField(max_length=512, blank=True, default="")
    photo_content_type = models.CharField(max_length=20, blank=True, default="")
    # A requested upload that has not been completed yet; never exposed
    pending_photo_key = models.CharField(max_length=512, blank=True, default="")
    pending_photo_content_type = models.CharField(max_length=20, blank=True, default="")
    pending_photo_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    # When the pending upload was requested (stale pending uploads are purged)
    pending_photo_requested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Oldest first: the frontend appends a newly created pet to its list
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["owner", "created_at"], name="pets_pet_owner_created_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(microchip_no="") | Q(microchip_no__regex=r"^[0-9]{15}$"),
                name="pets_pet_microchip_format",
            ),
            models.CheckConstraint(
                condition=Q(weight_kg__isnull=True) | Q(weight_kg__gt=0),
                name="pets_pet_weight_positive",
            ),
        ]

    def __str__(self):
        return self.name


class HealthRecord(models.Model):
    VACCINATION = "vaccination"
    DEWORMING = "deworming"
    GROOMING = "grooming"
    CHECKUP = "checkup"
    OTHER = "other"
    RECORD_TYPE_CHOICES = [
        (VACCINATION, "Vaccination"),
        (DEWORMING, "Deworming"),
        (GROOMING, "Grooming"),
        (CHECKUP, "Check-up"),
        (OTHER, "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE, related_name="records")
    record_type = models.CharField(max_length=12, choices=RECORD_TYPE_CHOICES)
    name = models.CharField(max_length=100)
    date = models.DateField()
    next_due = models.DateField(null=True, blank=True)
    # Free text; never a link to the facilities registry
    clinic = models.CharField(max_length=100, blank=True, default="")
    # At most 1000 characters, enforced by the serializer
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["pet", "-date"], name="pets_record_pet_date_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(next_due__isnull=True) | Q(next_due__gte=F("date")),
                name="pets_record_next_due_gte_date",
            )
        ]

    def __str__(self):
        return f"{self.get_record_type_display()}: {self.name}"


class PetDocument(models.Model):
    """A private vet report. There is no file name column: keys and rows carry
    no user-supplied file names."""

    PDF = "application/pdf"
    JPEG = "image/jpeg"
    PNG = "image/png"
    CONTENT_TYPE_CHOICES = [(PDF, "PDF"), (JPEG, "JPEG"), (PNG, "PNG")]

    PENDING = "pending"
    READY = "ready"
    STATUS_CHOICES = [(PENDING, "Pending"), (READY, "Ready")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE, related_name="documents")
    health_record = models.ForeignKey(
        HealthRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    title = models.CharField(max_length=150)
    file_key = models.CharField(max_length=512, unique=True)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    size_bytes = models.PositiveIntegerField()
    status = models.CharField(max_length=7, choices=STATUS_CHOICES, default=PENDING)
    # Set when the upload is completed
    uploaded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "-created_at"]
        indexes = [
            models.Index(fields=["pet", "status"], name="pets_doc_pet_status_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(size_bytes__gte=1) & Q(size_bytes__lte=10485760),
                name="pets_doc_size_range",
            )
        ]

    def __str__(self):
        return self.title


class Reminder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE, related_name="reminders")
    health_record = models.ForeignKey(
        HealthRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reminders",
    )
    title = models.CharField(max_length=150)
    due_at = models.DateTimeField()
    done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_at", "created_at", "id"]
        indexes = [
            models.Index(fields=["pet", "due_at"], name="pets_reminder_pet_due_idx")
        ]

    def __str__(self):
        return self.title
