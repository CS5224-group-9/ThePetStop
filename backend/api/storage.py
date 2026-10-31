"""Private pet file storage behind one interface.

`settings.PET_FILES_BACKEND` (read on every call) picks the backend:

- "s3": the private PetFiles bucket, with presigned PUT/GET URLs (boto3);
- "local": DEBUG only, files under PET_FILES_LOCAL_DIR served by
  `api.local_files` through Django-signed, expiring URLs on this server;
- "disabled": every operation raises StorageUnavailable (503).

Callers store keys, never URLs. Never log URLs, tokens, keys, titles or medical
text: log only the operation and the exception class or S3 error code.
"""

import functools
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from rest_framework.exceptions import APIException

logger = logging.getLogger("api.storage")

# Signing salt of local file tokens; api.local_files verifies with the same salt
LOCAL_SALT = "api.local_files"

_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,511}")
_MISSING_CODES = {"404", "NoSuchKey", "NotFound"}
_FORBIDDEN_CODES = {"403", "AccessDenied", "Forbidden"}


class StorageUnavailable(APIException):
    status_code = 503
    default_code = "storage_unavailable"
    default_detail = "File storage is unavailable. Please try again later."


@dataclass(frozen=True)
class StoredObject:
    size: int
    content_type: str


def validate_key(key: str) -> str:
    """Return the key if it is a safe relative object key; else ValueError.

    A bad key is a server bug (keys are built by the server), not a 4xx.
    """
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("Invalid pet file key.")
    segments = key.split("/")
    if "//" in key or key.endswith("/") or any(s in {".", ".."} for s in segments):
        raise ValueError("Invalid pet file key.")
    return key


def presign_put(
    key: str, *, content_type: str, size_bytes: int, expires_in: int = 900
) -> str:
    """URL for one PUT of exactly this Content-Type and Content-Length."""
    validate_key(key)
    return _backend().presign_put(
        key, content_type=content_type, size_bytes=size_bytes, expires_in=expires_in
    )


def presign_get(
    key: str, *, content_type: str, disposition: str, expires_in: int = 300
) -> str:
    """Short-lived download URL, served with this type and disposition."""
    validate_key(key)
    return _backend().presign_get(
        key, content_type=content_type, disposition=disposition, expires_in=expires_in
    )


def head(key: str) -> StoredObject | None:
    """Size and type of the stored object, or None when it is absent."""
    validate_key(key)
    return _backend().head(key)


def delete(key: str) -> None:
    """Delete the object. Idempotent: an absent object is fine."""
    validate_key(key)
    _backend().delete(key)


def delete_on_commit(*keys: str) -> None:
    """Delete these objects after the current transaction commits (immediately
    outside one). Best effort: never raises; failures are logged by class."""
    keys = [key for key in keys if key]
    if not keys:
        return

    def cleanup():
        for key in keys:
            try:
                # Module-level lookup at call time, so tests can patch it
                delete(key)
            except Exception as exc:
                logger.warning("Pet file cleanup failed: %s", exc.__class__.__name__)

    transaction.on_commit(cleanup)


def _backend():
    name = settings.PET_FILES_BACKEND
    if name == "s3":
        return _S3
    if name == "local":
        return _LOCAL
    if name == "disabled":
        raise StorageUnavailable
    raise ImproperlyConfigured(f"Unknown PET_FILES_BACKEND {name!r}.")


# S3


@functools.cache
def _s3_client(region: str, endpoint_url: str):
    # A fresh session per client: boto3's default session caches the credentials
    # it resolves first, which would survive a cache_clear().
    return boto3.session.Session().client(
        "s3",
        region_name=region,
        endpoint_url=endpoint_url or None,
        config=Config(
            signature_version="s3v4",
            # Emulators on localhost cannot resolve bucket subdomains
            s3={"addressing_style": "path" if endpoint_url else "virtual"},
            # No checksum headers or parameters: the bucket CORS allows only
            # content-type, so the browser could not send them
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            connect_timeout=3,
            read_timeout=5,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def _error_code(exc) -> str:
    if isinstance(exc, ClientError):
        return str(exc.response.get("Error", {}).get("Code", "")) or "ClientError"
    return exc.__class__.__name__


def _unavailable(op, exc):
    logger.warning("Pet file %s failed: %s", op, _error_code(exc))
    return StorageUnavailable()


class _S3Backend:
    """Credentials come from the default chain: the Lambda role in AWS, or the
    developer's profile locally."""

    @staticmethod
    def client():
        return _s3_client(settings.PET_FILES_REGION, settings.PET_FILES_ENDPOINT_URL)

    def presign_put(self, key, *, content_type, size_bytes, expires_in):
        try:
            return self.client().generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.PET_FILES_BUCKET,
                    "Key": key,
                    "ContentType": content_type,
                    "ContentLength": size_bytes,
                },
                ExpiresIn=expires_in,
                HttpMethod="PUT",
            )
        except (BotoCoreError, ClientError) as exc:
            raise _unavailable("presign_put", exc) from exc

    def presign_get(self, key, *, content_type, disposition, expires_in):
        try:
            return self.client().generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.PET_FILES_BUCKET,
                    "Key": key,
                    "ResponseContentType": content_type,
                    "ResponseContentDisposition": disposition,
                    "ResponseCacheControl": "private, no-store",
                },
                ExpiresIn=expires_in,
            )
        except (BotoCoreError, ClientError) as exc:
            raise _unavailable("presign_get", exc) from exc

    def head(self, key):
        try:
            response = self.client().head_object(
                Bucket=settings.PET_FILES_BUCKET, Key=key
            )
        except ClientError as exc:
            code = _error_code(exc)
            if code in _MISSING_CODES:
                return None
            if code in _FORBIDDEN_CODES:
                # Without s3:ListBucket, S3 answers a missing object with 403. A
                # run of these after successful PUTs means s3:GetObject is missing.
                logger.info("Pet file head returned %s", code)
                return None
            raise _unavailable("head", exc) from exc
        except BotoCoreError as exc:
            raise _unavailable("head", exc) from exc
        return StoredObject(
            size=response["ContentLength"],
            content_type=response.get("ContentType", ""),
        )

    def delete(self, key):
        try:
            self.client().delete_object(Bucket=settings.PET_FILES_BUCKET, Key=key)
        except ClientError as exc:
            if _error_code(exc) in _MISSING_CODES:
                return
            raise _unavailable("delete", exc) from exc
        except BotoCoreError as exc:
            raise _unavailable("delete", exc) from exc


# Local (DEBUG only)


class _LocalBackend:
    """Files under PET_FILES_LOCAL_DIR, each with a `<file>.meta` JSON sidecar
    holding {"content_type", "size"}. URLs point at api.local_files and carry a
    signed, expiring token. Settings are read on every call, not at import."""

    @staticmethod
    def resolve(key: str) -> Path:
        """The file path of a key. Every filesystem access goes through here."""
        root = Path(settings.PET_FILES_LOCAL_DIR).resolve()
        path = (root / validate_key(key)).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Pet file key is outside the local storage folder.")
        return path

    @staticmethod
    def meta_path(path: Path) -> Path:
        return path.with_name(f"{path.name}.meta")

    def write_meta(self, path: Path, *, content_type: str, size: int) -> None:
        """Atomically write the sidecar of a stored file."""
        meta = json.dumps({"content_type": content_type, "size": size})
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".meta-", suffix=".part")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.write(meta)
            os.replace(tmp, self.meta_path(path))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @staticmethod
    def _url(payload: dict, expires_in: int) -> str:
        payload = {**payload, "exp": int(time.time()) + expires_in}
        token = signing.dumps(payload, salt=LOCAL_SALT, compress=True)
        # PET_FILES_LOCAL_URL always ends in "/" (settings normalise it)
        return f"{settings.PET_FILES_LOCAL_URL}{token}/"

    def presign_put(self, key, *, content_type, size_bytes, expires_in):
        self.resolve(key)
        return self._url(
            {"k": key, "m": "PUT", "ct": content_type, "n": size_bytes}, expires_in
        )

    def presign_get(self, key, *, content_type, disposition, expires_in):
        self.resolve(key)
        return self._url(
            {"k": key, "m": "GET", "ct": content_type, "cd": disposition}, expires_in
        )

    def head(self, key):
        path = self.resolve(key)
        try:
            meta = json.loads(self.meta_path(path).read_text(encoding="utf-8"))
            stored = StoredObject(
                size=int(meta["size"]), content_type=str(meta["content_type"])
            )
        except FileNotFoundError:
            return None
        except (ValueError, KeyError, TypeError):
            # A half-written or damaged sidecar: treat the upload as not finished
            return None
        except OSError as exc:
            raise _unavailable("head", exc) from exc
        return stored if path.is_file() else None

    def delete(self, key):
        path = self.resolve(key)
        try:
            path.unlink(missing_ok=True)
            self.meta_path(path).unlink(missing_ok=True)
        except OSError as exc:
            raise _unavailable("delete", exc) from exc


_S3 = _S3Backend()
_LOCAL = _LocalBackend()
