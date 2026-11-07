"""Pet file keys, upload tickets, completion checks and presigned download URLs.

Uploads are three steps: the API returns a presigned PUT signed for the exact
Content-Type and Content-Length, the browser PUTs the bytes straight to storage,
then a `complete` call checks the stored object before it becomes visible.

Keys contain only UUIDs, never titles or file names. Every storage call goes
through `storage.<fn>(...)` (looked up at call time) so tests can patch
`api.storage`. Never log URLs, keys or titles.
"""

import uuid
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Literal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from api import storage

from .models import Pet, PetDocument

DOCUMENT_TYPES = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}
PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png"}
DOCUMENT_MAX_BYTES = 10 * 1024 * 1024
PHOTO_MAX_BYTES = 5 * 1024 * 1024
PUT_EXPIRES = 900
DOCUMENT_GET_EXPIRES = 300
PHOTO_GET_EXPIRES = 3600
PENDING_UPLOAD_TTL = timedelta(hours=1)


class UploadIncomplete(APIException):
    status_code = 409
    default_code = "upload_incomplete"
    default_detail = "The file has not finished uploading. Try again."


class UploadInvalid(APIException):
    status_code = 400
    default_code = "upload_invalid"
    default_detail = (
        "The uploaded file does not match the declared type or size. Upload it again."
    )


def document_key(pet_id, document_id, content_type) -> str:
    return f"pets/{pet_id}/documents/{document_id}.{DOCUMENT_TYPES[content_type]}"


def photo_key(pet_id, content_type) -> str:
    # A new UUID for every upload, so the key (and photo_version) changes
    return f"pets/{pet_id}/photos/{uuid.uuid4()}.{PHOTO_TYPES[content_type]}"


def upload_ticket(key, content_type, size_bytes) -> dict:
    """Upload instructions. Raises StorageUnavailable (503) before any DB write."""
    return {
        "upload_url": storage.presign_put(
            key,
            content_type=content_type,
            size_bytes=size_bytes,
            expires_in=PUT_EXPIRES,
        ),
        "upload_headers": {"Content-Type": content_type},
    }


def check_upload(key, content_type, size_bytes) -> Literal["ok", "missing", "mismatch"]:
    """Compare the stored object with the declared type and size. Makes a storage
    network call, so never call it inside a transaction."""
    stored = storage.head(key)
    if stored is None:
        return "missing"
    stored_type = stored.content_type.split(";")[0].strip().lower()
    if stored.size != size_bytes or stored_type != content_type:
        return "mismatch"
    return "ok"


def document_download_url(doc) -> str | None:
    """A short-lived download URL for a completed document; None while pending or
    when storage is unavailable."""
    if doc.status != PetDocument.READY:
        return None
    ext = DOCUMENT_TYPES[doc.content_type]
    try:
        return storage.presign_get(
            doc.file_key,
            content_type=doc.content_type,
            disposition=f'attachment; filename="pet-document.{ext}"',
            expires_in=DOCUMENT_GET_EXPIRES,
        )
    except storage.StorageUnavailable:
        return None


def photo_url(pet) -> str | None:
    """A presigned URL for the completed photo; None without a photo or when
    storage is unavailable. Pending photos are never exposed."""
    if not pet.photo_key:
        return None
    try:
        return storage.presign_get(
            pet.photo_key,
            content_type=pet.photo_content_type,
            disposition="inline",
            expires_in=PHOTO_GET_EXPIRES,
        )
    except storage.StorageUnavailable:
        return None


def photo_version(pet) -> str | None:
    """The UUID stem of the completed photo's key: changes only with the photo."""
    return PurePosixPath(pet.photo_key).stem if pet.photo_key else None


def purge_stale_pending(owner) -> None:
    """Discard this owner's uploads requested more than PENDING_UPLOAD_TTL ago and
    never completed, with their stored objects (deleted after commit).

    Called only when the owner requests a new document or photo upload, so reads
    stay free of side effects.
    """
    cutoff = timezone.now() - PENDING_UPLOAD_TTL
    with transaction.atomic():
        docs = PetDocument.objects.filter(
            pet__owner=owner, status=PetDocument.PENDING, created_at__lt=cutoff
        )
        doc_keys = list(docs.values_list("file_key", flat=True))
        docs.delete()
        stale = (
            Pet.objects.select_for_update()
            .filter(owner=owner, pending_photo_requested_at__lt=cutoff)
            .exclude(pending_photo_key="")
        )
        rows = list(stale.values_list("pk", "pending_photo_key"))
        Pet.objects.filter(pk__in=[pk for pk, _ in rows]).update(
            pending_photo_key="",
            pending_photo_content_type="",
            pending_photo_size_bytes=None,
            pending_photo_requested_at=None,
        )
        storage.delete_on_commit(*doc_keys, *(key for _, key in rows))
