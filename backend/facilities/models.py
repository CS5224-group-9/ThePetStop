import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone


class FacilitySource(models.TextChoices):
    VET = "vet", "AVS licensed veterinary centres"
    PET_SHOP = "pet_shop", "AVS licensed pet shops"


class FacilitySyncRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        SUPERSEDED = "superseded", "Superseded"
        REVIEW_REQUIRED = "review_required", "Review required"

    run_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=16, choices=FacilitySource.choices)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.RUNNING
    )
    stage = models.CharField(max_length=24, default="fetching")
    last_activity_at = models.DateTimeField(null=True, blank=True)
    expected_batch_count = models.PositiveIntegerField(default=0)
    completed_batch_count = models.PositiveIntegerField(default=0)
    retry_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    registry_url = models.URLField(max_length=1000, blank=True)
    document_url = models.URLField(max_length=1000, blank=True)
    published_at = models.DateField(null=True, blank=True)
    document_sha256 = models.CharField(max_length=64, blank=True)
    parsed_count = models.PositiveIntegerField(default=0)
    inserted_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unchanged_count = models.PositiveIntegerField(default=0)
    deactivated_count = models.PositiveIntegerField(default=0)
    unlocated_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.source} sync {self.run_id} ({self.status})"


class FacilitySyncEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        FacilitySyncRun,
        on_delete=models.CASCADE,
        related_name="events",
    )
    stage = models.CharField(max_length=24)
    kind = models.CharField(max_length=48)
    detail = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["occurred_at", "event_id"]
        indexes = [models.Index(fields=["run", "occurred_at"])]

    def __str__(self):
        return f"{self.run_id}: {self.stage}/{self.kind}"


class FacilitySourceState(models.Model):
    source = models.CharField(
        max_length=16,
        choices=FacilitySource.choices,
        primary_key=True,
    )
    latest_successful_run = models.ForeignKey(
        FacilitySyncRun,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="current_source_states",
    )
    last_checked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.get_source_display()


class Facility(models.Model):
    class Type(models.TextChoices):
        VET = "vet", "Veterinary centre"
        PET_SHOP = "pet_shop", "Pet shop"

    class GeocodeStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        RESOLVED = "resolved", "Resolved"
        UNLOCATED = "unlocated", "Unlocated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_id = models.CharField(max_length=16, choices=FacilitySource.choices)
    source_key = models.CharField(max_length=64)
    facility_type = models.CharField(max_length=16, choices=Type.choices)
    name = models.CharField(max_length=240)
    licence_no = models.CharField(max_length=32, blank=True, default="")
    address = models.TextField()
    postal_code = models.CharField(max_length=6)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(max_length=1000, blank=True)
    source = models.CharField(max_length=120)
    source_url = models.URLField(max_length=1000)
    source_document_url = models.URLField(max_length=1000)
    source_published_at = models.DateField(null=True, blank=True)
    last_checked_at = models.DateTimeField()
    geocode_status = models.CharField(
        max_length=12,
        choices=GeocodeStatus.choices,
        default=GeocodeStatus.PENDING,
    )
    geocode_query = models.CharField(max_length=500, blank=True)
    geocode_provider = models.CharField(max_length=40, blank=True)
    geocoded_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    last_seen_run = models.ForeignKey(
        FacilitySyncRun,
        on_delete=models.PROTECT,
        related_name="facilities_seen",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_id", "source_key"],
                name="fac_source_key_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(latitude__isnull=True, longitude__isnull=True)
                    | Q(latitude__isnull=False, longitude__isnull=False)
                ),
                name="fac_coords_both_or_neither",
            ),
        ]
        indexes = [
            models.Index(
                fields=["active", "facility_type"], name="fac_active_type_idx"
            ),
            models.Index(fields=["postal_code"], name="fac_postal_idx"),
            models.Index(fields=["latitude", "longitude"], name="fac_coords_idx"),
        ]
        ordering = ["name", "id"]

    def __str__(self):
        return self.name
