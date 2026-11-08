"""Owner-scoped pets API (docs/openapi/pets.yaml).

Every queryset is filtered by the authenticated user, so another owner's object
in a URL is a 404, never a 403. There is no group gate: merchants may own pets.

Storage network calls (`head`) always run outside a transaction, and every write
after one uses a row lock or a conditional UPDATE: Django's save() INSERTs when
its UPDATE matches no row, which would bring back a row deleted meanwhile.
"""

import uuid
from contextlib import contextmanager

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from api import storage

from . import reminders, uploads
from .models import HealthRecord, Pet, PetDocument, Reminder
from .serializers import (
    DocumentUploadRequestSerializer,
    HealthRecordSerializer,
    PetDocumentSerializer,
    PetSerializer,
    PhotoUploadRequestSerializer,
    ReminderQuerySerializer,
    ReminderSerializer,
)

CONFLICT_MESSAGE = "This item changed. Refresh and try again."

# Detail routes: PATCH only, so PUT is a 405
DETAIL_METHODS = ["get", "patch", "delete", "head", "options"]

PHOTO_FIELDS = [
    "photo_key",
    "photo_content_type",
    "pending_photo_key",
    "pending_photo_content_type",
    "pending_photo_size_bytes",
    "pending_photo_requested_at",
]
CLEAR_PENDING_PHOTO = {
    "pending_photo_key": "",
    "pending_photo_content_type": "",
    "pending_photo_size_bytes": None,
    "pending_photo_requested_at": None,
}
PENDING_PHOTO_FIELDS = list(CLEAR_PENDING_PHOTO)


class NoStoreMixin:
    """Private data: every response, errors included, is `no-store`."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class OwnedPetMixin(NoStoreMixin):
    """Views under pets/<pet_pk>/: the pet must be the user's (else 404)."""

    def get_pet(self):
        if not hasattr(self, "_pet"):
            self._pet = get_object_or_404(
                Pet.objects.filter(owner=self.request.user), pk=self.kwargs["pet_pk"]
            )
        return self._pet

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "pet": self.get_pet()}


def lock_pet(user, pk) -> Pet:
    """Call inside transaction.atomic(). Row-locks the owner's pet; 404 if it is gone."""
    return get_object_or_404(Pet.objects.select_for_update().filter(owner=user), pk=pk)


@contextmanager
def integrity_guard(pet=None):
    """Turn a DB IntegrityError into a clean 4xx. Never let the DB message escape
    (Postgres puts the failing row, including medical text, in it).

    Foreign keys are checked at commit (Django makes them DEFERRABLE INITIALLY
    DEFERRED), so as the outermost transaction this also catches a child insert
    whose pet was deleted meanwhile: that is a 404.
    """
    try:
        with transaction.atomic():
            yield
    except IntegrityError:
        if pet is not None and not Pet.objects.filter(pk=pet.pk).exists():
            raise NotFound from None
        raise ValidationError({"non_field_errors": [CONFLICT_MESSAGE]}) from None


# Pets


class PetListCreateView(NoStoreMixin, generics.ListCreateAPIView):
    serializer_class = PetSerializer

    def get_queryset(self):
        # Read-only: listing never purges or changes anything
        return Pet.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        # The owner is never read from the body
        with integrity_guard():
            serializer.save(owner=self.request.user)


class PetDetailView(NoStoreMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PetSerializer
    http_method_names = DETAIL_METHODS

    def get_queryset(self):
        queryset = Pet.objects.filter(owner=self.request.user)
        if self.request.method == "PATCH":
            # save() writes every column: read the row under a lock so a photo
            # completed meanwhile is not overwritten with stale keys
            queryset = queryset.select_for_update()
        return queryset

    def update(self, request, *args, **kwargs):
        # One transaction around the locked read, validation and save
        with integrity_guard():
            return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        with integrity_guard():
            serializer.save()

    def perform_destroy(self, instance):
        with transaction.atomic():
            # Blocks concurrent child inserts (FK KEY SHARE) until commit
            pet = lock_pet(self.request.user, instance.pk)
            keys = [
                key
                for key in [
                    pet.photo_key,
                    pet.pending_photo_key,
                    *pet.documents.values_list("file_key", flat=True),
                ]
                if key
            ]
            pet.delete()  # cascades records, documents and reminders
            storage.delete_on_commit(*keys)


class PetPhotoUploadView(NoStoreMixin, generics.GenericAPIView):
    serializer_class = PhotoUploadRequestSerializer

    def get_queryset(self):
        return Pet.objects.filter(owner=self.request.user)

    def post(self, request, *args, **kwargs):
        pet = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content_type = serializer.validated_data["content_type"]
        size = serializer.validated_data["size_bytes"]
        key = uploads.photo_key(pet.id, content_type)
        # A 503 propagates here, before any DB change
        ticket = uploads.upload_ticket(key, content_type, size)
        uploads.purge_stale_pending(request.user)
        with transaction.atomic():
            locked = lock_pet(request.user, pet.pk)
            old = locked.pending_photo_key
            locked.pending_photo_key = key
            locked.pending_photo_content_type = content_type
            locked.pending_photo_size_bytes = size
            locked.pending_photo_requested_at = timezone.now()
            locked.save(update_fields=PENDING_PHOTO_FIELDS)
            if old:
                # Replaced before it was completed
                storage.delete_on_commit(old)
        return Response(ticket)


class PetPhotoCompleteView(NoStoreMixin, generics.GenericAPIView):
    serializer_class = PetSerializer

    def get_queryset(self):
        return Pet.objects.filter(owner=self.request.user)

    def post(self, request, *args, **kwargs):
        pet = self.get_object()
        key = pet.pending_photo_key
        content_type = pet.pending_photo_content_type
        size = pet.pending_photo_size_bytes
        if not key:
            raise uploads.UploadIncomplete
        # Storage call outside any transaction; a 503 propagates
        result = uploads.check_upload(key, content_type, size)
        invalid = False
        with transaction.atomic():
            locked = lock_pet(request.user, pet.pk)  # 404 if deleted meanwhile
            if locked.pending_photo_key != key or result == "missing":
                # Replaced or cleared meanwhile, or not stored yet
                raise uploads.UploadIncomplete
            for field, value in CLEAR_PENDING_PHOTO.items():
                setattr(locked, field, value)
            if result == "mismatch":
                locked.save(update_fields=PENDING_PHOTO_FIELDS)
                storage.delete_on_commit(key)
                invalid = True
            else:
                old = locked.photo_key
                locked.photo_key = key
                locked.photo_content_type = content_type
                locked.save(
                    update_fields=[
                        "photo_key",
                        "photo_content_type",
                        *PENDING_PHOTO_FIELDS,
                        "updated_at",
                    ]
                )
                if old:
                    storage.delete_on_commit(old)
        if invalid:
            # Raised after commit, so the clearing is kept
            raise uploads.UploadInvalid
        # A fresh photo_url and the new photo_version
        return Response(self.get_serializer(locked).data)


class PetPhotoView(NoStoreMixin, generics.GenericAPIView):
    serializer_class = PetSerializer

    def get_queryset(self):
        return Pet.objects.filter(owner=self.request.user)

    def delete(self, request, *args, **kwargs):
        pet = self.get_object()
        with transaction.atomic():
            locked = lock_pet(request.user, pet.pk)
            keys = [k for k in [locked.photo_key, locked.pending_photo_key] if k]
            locked.photo_key = ""
            locked.photo_content_type = ""
            for field, value in CLEAR_PENDING_PHOTO.items():
                setattr(locked, field, value)
            locked.save(update_fields=[*PHOTO_FIELDS, "updated_at"])
            storage.delete_on_commit(*keys)
        return Response(status=status.HTTP_204_NO_CONTENT)


# Health records


class HealthRecordListCreateView(OwnedPetMixin, generics.ListCreateAPIView):
    serializer_class = HealthRecordSerializer

    def get_queryset(self):
        return HealthRecord.objects.filter(pet=self.get_pet())

    def perform_create(self, serializer):
        # Saving a next_due never creates a reminder
        with integrity_guard(self.get_pet()):
            serializer.save(pet=self.get_pet())


class HealthRecordDetailView(OwnedPetMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = HealthRecordSerializer
    http_method_names = DETAIL_METHODS

    def get_queryset(self):
        queryset = HealthRecord.objects.filter(pet=self.get_pet())
        if self.request.method == "PATCH":
            queryset = queryset.select_for_update()
        return queryset

    def update(self, request, *args, **kwargs):
        # One transaction: the row is locked, so the merged-value validation
        # sees fresh values
        with integrity_guard(self.get_pet()):
            return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        with integrity_guard(self.get_pet()):
            serializer.save()


# Documents


class DocumentListCreateView(OwnedPetMixin, generics.ListCreateAPIView):
    def get_queryset(self):
        # Pending uploads are never listed
        return PetDocument.objects.filter(pet=self.get_pet(), status=PetDocument.READY)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DocumentUploadRequestSerializer
        return PetDocumentSerializer

    def create(self, request, *args, **kwargs):
        pet = self.get_pet()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        doc_id = uuid.uuid4()
        key = uploads.document_key(pet.id, doc_id, data["content_type"])
        # A 503 propagates here, before any DB write
        ticket = uploads.upload_ticket(key, data["content_type"], data["size_bytes"])
        uploads.purge_stale_pending(request.user)
        with integrity_guard(pet):
            doc = PetDocument.objects.create(
                id=doc_id,
                pet=pet,
                title=data["title"],
                content_type=data["content_type"],
                size_bytes=data["size_bytes"],
                health_record=data.get("health_record"),
                status=PetDocument.PENDING,
                file_key=key,
            )
        document = PetDocumentSerializer(doc, context=self.get_serializer_context())
        return Response(
            {"document": document.data, **ticket}, status=status.HTTP_201_CREATED
        )


class DocumentDetailView(OwnedPetMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PetDocumentSerializer
    http_method_names = DETAIL_METHODS

    def get_queryset(self):
        queryset = PetDocument.objects.filter(pet=self.get_pet())
        if self.request.method == "DELETE":
            # Pending documents can be deleted (cleanup after a failed upload)
            return queryset
        queryset = queryset.filter(status=PetDocument.READY)
        if self.request.method == "PATCH":
            queryset = queryset.select_for_update()
        return queryset

    def update(self, request, *args, **kwargs):
        with integrity_guard(self.get_pet()):
            return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        with integrity_guard(self.get_pet()):
            serializer.save()

    def perform_destroy(self, instance):
        key = instance.file_key
        instance.delete()
        storage.delete_on_commit(key)


class DocumentCompleteView(OwnedPetMixin, generics.GenericAPIView):
    serializer_class = PetDocumentSerializer

    def get_queryset(self):
        return PetDocument.objects.filter(pet=self.get_pet())

    def post(self, request, *args, **kwargs):
        pet = self.get_pet()
        doc = self.get_object()
        if doc.status == PetDocument.READY:
            # Idempotent: no storage call
            return Response(self.get_serializer(doc).data)
        # Storage call outside any transaction; a 503 propagates
        result = uploads.check_upload(doc.file_key, doc.content_type, doc.size_bytes)
        if result == "missing":
            raise uploads.UploadIncomplete  # the row stays pending
        pending = PetDocument.objects.filter(pk=doc.pk, status=PetDocument.PENDING)
        if result == "mismatch":
            deleted, _ = pending.delete()
            if deleted:
                storage.delete_on_commit(doc.file_key)
            raise uploads.UploadInvalid
        # Conditional UPDATE: never re-inserts a row deleted meanwhile
        pending.update(status=PetDocument.READY, uploaded_at=timezone.now())
        doc = PetDocument.objects.filter(
            pk=doc.pk, pet=pet, status=PetDocument.READY
        ).first()
        if doc is None:
            raise NotFound  # deleted while it was being checked
        return Response(self.get_serializer(doc).data)


# Reminders


class ReminderListCreateView(NoStoreMixin, generics.ListCreateAPIView):
    serializer_class = ReminderSerializer

    def get_queryset(self):
        queryset = reminders.owner_reminders(self.request.user)
        params = ReminderQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        pet = params.validated_data.get("pet")
        done = params.validated_data.get("done")
        if pet is not None:
            # Another owner's pet simply matches nothing
            queryset = queryset.filter(pet=pet)
        if done is not None:
            queryset = queryset.filter(done=done)
        return queryset

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "today": reminders.today_sgt()}

    def perform_create(self, serializer):
        pet = serializer.validated_data.get("pet") or getattr(
            serializer.instance, "pet", None
        )
        with integrity_guard(pet):
            serializer.save()


class ReminderDetailView(NoStoreMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ReminderSerializer
    http_method_names = DETAIL_METHODS

    def get_queryset(self):
        queryset = Reminder.objects.filter(pet__owner=self.request.user)
        if self.request.method == "PATCH":
            # Lock only the reminder row, not the joined pet
            queryset = queryset.select_for_update(of=("self",))
        return queryset

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "today": reminders.today_sgt()}

    def update(self, request, *args, **kwargs):
        with integrity_guard():
            return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        pet = serializer.validated_data.get("pet") or getattr(
            serializer.instance, "pet", None
        )
        with integrity_guard(pet):
            serializer.save()
