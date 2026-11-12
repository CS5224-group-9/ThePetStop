"""Presigned uploads for merchant catalogue images."""

import functools
import os
import re
import uuid
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from rest_framework.exceptions import APIException, ValidationError

IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
UPLOAD_EXPIRES = 900


class ImageStorageUnavailable(APIException):
    status_code = 503
    default_code = "image_storage_unavailable"
    default_detail = "Product image storage is unavailable. Please try again later."


@dataclass(frozen=True)
class Upload:
    key: str
    url: str


def validate_upload(content_type, size_bytes):
    if content_type not in IMAGE_TYPES:
        raise ValidationError({"content_type": ["Upload a JPEG, PNG or WebP image."]})
    if not isinstance(size_bytes, int) or not 1 <= size_bytes <= MAX_IMAGE_BYTES:
        raise ValidationError(
            {"size_bytes": ["Image must be between 1 byte and 5 MB."]}
        )


def image_key(merchant_id, product_id, content_type):
    extension = IMAGE_TYPES[content_type]
    return f"product-images/merchant-uploads/{merchant_id}/{product_id}/{uuid.uuid4()}.{extension}"


def upload_ticket(key, content_type, size_bytes):
    validate_upload(content_type, size_bytes)
    try:
        url = _client().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": _bucket(),
                "Key": key,
                "ContentType": content_type,
                "ContentLength": size_bytes,
            },
            ExpiresIn=UPLOAD_EXPIRES,
            HttpMethod="PUT",
        )
    except (BotoCoreError, ClientError) as exc:
        raise ImageStorageUnavailable from exc
    return Upload(key=key, url=url)


def verify_upload(key, content_type, size_bytes):
    validate_upload(content_type, size_bytes)
    try:
        response = _client().head_object(Bucket=_bucket(), Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        if code in {"403", "AccessDenied", "Forbidden"}:
            raise ImageStorageUnavailable from exc
        raise ImageStorageUnavailable from exc
    except BotoCoreError as exc:
        raise ImageStorageUnavailable from exc
    stored_type = response.get("ContentType", "").split(";")[0].strip().lower()
    return response.get("ContentLength") == size_bytes and stored_type == content_type


def _bucket():
    bucket = settings.PRODUCT_IMAGES_BUCKET_NAME
    if not bucket:
        raise ImageStorageUnavailable
    return bucket


@functools.cache
def _client():
    return boto3.session.Session().client(
        "s3",
        region_name=os.environ.get("AWS_REGION") or "ap-southeast-1",
        config=Config(
            signature_version="s3v4",
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            connect_timeout=3,
            read_timeout=5,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def validate_owned_key(key, merchant_id, product_id):
    prefix = f"product-images/merchant-uploads/{merchant_id}/{product_id}/"
    if (
        not isinstance(key, str)
        or not key.startswith(prefix)
        or not re.fullmatch(
            r"[A-Za-z0-9-]+\.(?:jpg|png|webp)", key.removeprefix(prefix), re.I
        )
    ):
        raise ValidationError(
            {"image_key": ["This upload does not belong to this product."]}
        )
    return key
