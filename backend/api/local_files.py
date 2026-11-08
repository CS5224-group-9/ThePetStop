"""Local development stand-in for presigned S3 URLs (the "local" storage backend).

`/api/v1/local-files/<token>/` is mounted only while the local backend is active
and answers loopback clients only. It is auth-free: the signed, expiring token
issued by `api.storage` is the capability, exactly like a presigned S3 URL. There
is no DRF, no session and no Authorization header.
"""

import os
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.http import FileResponse, HttpResponse, JsonResponse
from django.urls import re_path
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from api import storage
from api.authentication import LOOPBACK_ADDRS

CHUNK_BYTES = 65536


def local_file_urlpatterns() -> list:
    """The local file route, or nothing unless the local backend is active."""
    if settings.PET_FILES_BACKEND != "local":
        return []
    # The trailing slash is optional, so CommonMiddleware never redirects (or, for
    # a PUT, raises) on a URL that carries the token
    return [
        re_path(r"^api/v1/local-files/(?P<token>[^/]+)/?$", serve, name="local-file")
    ]


def _error(status, code, message):
    return JsonResponse(
        {"error": {"code": code, "message": message, "details": {}}}, status=status
    )


def _mismatch():
    return _error(403, "signature_mismatch", "This file link is not valid.")


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def serve(request, token):
    if settings.PET_FILES_BACKEND != "local":
        return _error(404, "not_found", "Not found.")
    if request.META.get("REMOTE_ADDR") not in LOOPBACK_ADDRS:
        # The browser on this machine is the only legitimate client
        return _error(403, "forbidden", "Local files are served to this computer only.")

    try:
        payload = signing.loads(token, salt=storage.LOCAL_SALT)
    except signing.BadSignature:
        return _mismatch()
    try:
        key, method, content_type, expires = (
            payload["k"],
            payload["m"],
            payload["ct"],
            payload["exp"],
        )
        if not all(isinstance(v, str) for v in (key, method, content_type)):
            raise TypeError
        if type(expires) is not int:
            raise TypeError
        if not key.startswith("pets/"):
            raise ValueError
        file_path = storage._LOCAL.resolve(key)
    except (KeyError, TypeError, ValueError):
        return _mismatch()

    if time.time() > expires:
        return _error(403, "expired", "This file link has expired.")
    if request.method != method:
        return _mismatch()
    if method == "PUT":
        return _put(request, payload, file_path, content_type)
    return _get(payload, file_path, content_type)


def _put(request, payload, file_path: Path, content_type: str):
    size = payload.get("n")
    if type(size) is not int or size < 0:
        return _mismatch()
    # Both are signed, as for S3: request.content_type has its parameters stripped
    if request.content_type != content_type:
        return _mismatch()
    if request.META.get("CONTENT_LENGTH") != str(size):
        return _mismatch()

    file_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=file_path.parent, prefix=".upload-", suffix=".part")
    stored = False
    try:
        written = 0
        with os.fdopen(fd, "wb") as out:
            # Stream: request.body would raise RequestDataTooBig above 2.5 MB
            while chunk := request.read(CHUNK_BYTES):
                written += len(chunk)
                if written > size:
                    break
                out.write(chunk)
        if written != size:
            return _mismatch()
        os.replace(tmp, file_path)
        stored = True
        storage._LOCAL.write_meta(file_path, content_type=content_type, size=size)
    finally:
        if not stored:
            Path(tmp).unlink(missing_ok=True)
    return HttpResponse(status=200)


def _get(payload, file_path: Path, content_type: str):
    disposition = payload.get("cd")
    if not isinstance(disposition, str):
        return _mismatch()
    if not file_path.is_file():
        return _error(404, "not_found", "Not found.")
    # FileResponse closes the file when the response is closed
    response = FileResponse(open(file_path, "rb"), content_type=content_type)
    response["Content-Disposition"] = disposition
    response["Cache-Control"] = "no-store"
    return response
