"""Wire formats of the pets API (docs/openapi/pets.yaml).

Ownership rules that live here: every FK that is not writable is declared
read-only explicitly (ModelSerializer's default would accept any row in the
table), and writable FKs are scoped to the request's owner or pet, so a foreign
id behaves exactly like a nonexistent one.

`today` always comes from `reminders.today_sgt()` through the module, so tests
can patch `pets.reminders.today_sgt`.
"""

import re
from decimal import Decimal

from rest_framework import serializers
from rest_framework.fields import empty

from . import reminders, uploads
from .models import HealthRecord, Pet, PetDocument, Reminder

_MICROCHIP = re.compile(r"[0-9]{15}")


def does_not_exist_message(pk) -> str:
    """DRF's message for a nonexistent related id."""
    message = serializers.PrimaryKeyRelatedField.default_error_messages
    return message["does_not_exist"].format(pk_value=pk)


class MicrochipField(serializers.CharField):
    """Exactly 15 digits. Blank or null is stored as "" and shown as null."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 15)
        kwargs.setdefault("allow_blank", True)
        kwargs.setdefault("allow_null", True)
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def run_validation(self, data=empty):
        # null means "not recorded", the same as blank
        if data is None:
            data = ""
        return super().run_validation(data)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if value == "":
            return ""
        if not _MICROCHIP.fullmatch(value):
            raise serializers.ValidationError(
                "Enter exactly 15 digits, or leave it blank."
            )
        return value

    def to_representation(self, value):
        return value or None


class DueAtField(serializers.DateTimeField):
    """DRF lets OverflowError escape (a 500) for a naive datetime near year 1;
    report it as out of range, as it does for an aware one."""

    def enforce_timezone(self, value):
        try:
            return super().enforce_timezone(value)
        except OverflowError:
            self.fail("overflow")


class PetSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=50)
    species = serializers.ChoiceField(choices=Pet.SPECIES_CHOICES)
    breed = serializers.CharField(max_length=80, allow_blank=True, required=False)
    sex = serializers.ChoiceField(choices=Pet.SEX_CHOICES, required=False)
    date_of_birth = serializers.DateField(allow_null=True, required=False)
    microchip_no = MicrochipField()
    allergies = serializers.ListField(
        child=serializers.CharField(max_length=50),
        max_length=20,
        allow_empty=True,
        required=False,
    )
    diet_notes = serializers.CharField(max_length=500, allow_blank=True, required=False)
    weight_kg = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0.01"),
        max_value=Decimal("500"),
        allow_null=True,
        required=False,
        coerce_to_string=False,
    )
    photo_url = serializers.SerializerMethodField()
    photo_version = serializers.SerializerMethodField()

    class Meta:
        model = Pet
        fields = [
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
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_date_of_birth(self, value):
        if value and value > reminders.today_sgt():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate_allergies(self, value):
        # Drop case-insensitive duplicates, keeping the first spelling and order
        seen = set()
        unique = []
        for item in value:
            folded = item.casefold()
            if folded not in seen:
                seen.add(folded)
                unique.append(item)
        return unique

    def get_photo_url(self, obj):
        return uploads.photo_url(obj)

    def get_photo_version(self, obj):
        return uploads.photo_version(obj)


class HealthRecordSerializer(serializers.ModelSerializer):
    # The pet comes from the URL; a body `pet` is ignored
    pet = serializers.PrimaryKeyRelatedField(read_only=True)
    name = serializers.CharField(max_length=100)
    record_type = serializers.ChoiceField(choices=HealthRecord.RECORD_TYPE_CHOICES)
    date = serializers.DateField()
    next_due = serializers.DateField(allow_null=True, required=False)
    clinic = serializers.CharField(max_length=100, allow_blank=True, required=False)
    notes = serializers.CharField(max_length=1000, allow_blank=True, required=False)

    class Meta:
        model = HealthRecord
        fields = [
            "id",
            "pet",
            "name",
            "record_type",
            "date",
            "next_due",
            "clinic",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_date(self, value):
        if value > reminders.today_sgt():
            raise serializers.ValidationError("Date of care cannot be in the future.")
        return value

    def validate(self, attrs):
        # Merged values, so a PATCH of only one of the two dates is checked too
        instance = self.instance
        date = attrs.get("date", instance.date if instance else None)
        if "next_due" in attrs:
            next_due = attrs["next_due"]
        else:
            next_due = instance.next_due if instance else None
        if date and next_due and next_due < date:
            raise serializers.ValidationError(
                {"next_due": ["Next due date cannot be before the date of care."]}
            )
        return attrs


class ReminderSerializer(serializers.ModelSerializer):
    # Querysets are scoped to the request's owner in __init__
    pet = serializers.PrimaryKeyRelatedField(queryset=Pet.objects.none())
    health_record = serializers.PrimaryKeyRelatedField(
        queryset=HealthRecord.objects.none(), allow_null=True, required=False
    )
    title = serializers.CharField(max_length=150)
    due_at = DueAtField()
    done = serializers.BooleanField(required=False)
    is_overdue = serializers.SerializerMethodField()
    is_due_soon = serializers.SerializerMethodField()

    class Meta:
        model = Reminder
        fields = [
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
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            self.fields["pet"].queryset = Pet.objects.filter(owner=request.user)
            self.fields["health_record"].queryset = HealthRecord.objects.filter(
                pet__owner=request.user
            )

    def _today(self):
        return self.context.get("today") or reminders.today_sgt()

    def get_is_overdue(self, obj):
        return reminders.is_overdue(obj, self._today())

    def get_is_due_soon(self, obj):
        return reminders.is_due_soon(obj, self._today())

    def validate(self, attrs):
        if self.instance and "pet" in attrs and attrs["pet"] != self.instance.pet:
            raise serializers.ValidationError(
                {"pet": ["A reminder cannot be moved to another pet."]}
            )
        pet = attrs.get("pet") or self.instance.pet
        record = attrs.get("health_record")
        if record is not None and record.pet_id != pet.id:
            # Another pet's record looks exactly like a nonexistent one
            raise serializers.ValidationError(
                {"health_record": [does_not_exist_message(record.pk)]}
            )
        return attrs


class PetDocumentSerializer(serializers.ModelSerializer):
    """Read and PATCH. Only `title` and `health_record` are writable; the stored
    key is never a field."""

    pet = serializers.PrimaryKeyRelatedField(read_only=True)
    health_record = serializers.PrimaryKeyRelatedField(
        queryset=HealthRecord.objects.none(), allow_null=True, required=False
    )
    title = serializers.CharField(max_length=150)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = PetDocument
        fields = [
            "id",
            "pet",
            "health_record",
            "title",
            "content_type",
            "size_bytes",
            "status",
            "uploaded_at",
            "created_at",
            "download_url",
        ]
        read_only_fields = [
            "id",
            "content_type",
            "size_bytes",
            "status",
            "uploaded_at",
            "created_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "pet" in self.context:
            self.fields["health_record"].queryset = HealthRecord.objects.filter(
                pet=self.context["pet"]
            )

    def get_download_url(self, obj):
        return uploads.document_download_url(obj)


class DocumentUploadRequestSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=150)
    # Accepted for compatibility, validated and then discarded: file names are
    # never stored and never appear in a storage key
    filename = serializers.CharField(max_length=255, allow_blank=True, required=False)
    content_type = serializers.ChoiceField(choices=list(uploads.DOCUMENT_TYPES))
    size_bytes = serializers.IntegerField(
        min_value=1, max_value=uploads.DOCUMENT_MAX_BYTES
    )
    health_record = serializers.PrimaryKeyRelatedField(
        queryset=HealthRecord.objects.none(), allow_null=True, required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "pet" in self.context:
            self.fields["health_record"].queryset = HealthRecord.objects.filter(
                pet=self.context["pet"]
            )


class PhotoUploadRequestSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=list(uploads.PHOTO_TYPES))
    size_bytes = serializers.IntegerField(
        min_value=1, max_value=uploads.PHOTO_MAX_BYTES
    )


class ReminderQuerySerializer(serializers.Serializer):
    """GET /reminders/ filters. A missing `done` is None (no filter)."""

    pet = serializers.UUIDField(required=False)
    done = serializers.BooleanField(required=False, allow_null=True, default=None)
