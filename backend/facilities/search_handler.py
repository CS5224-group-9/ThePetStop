"""Public HTTP API v2 search handler; no Django setup or database access."""

import json
import logging
import os
import time
from urllib.parse import parse_qs

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from facilities.onemap import (
    OneMapClient,
    SearchFailed,
    SearchTimeout,
    SearchUnavailable,
)

logger = logging.getLogger(__name__)
_secret = None
_secret_until = 0


def credentials():
    global _secret, _secret_until
    if _secret is not None and time.monotonic() < _secret_until:
        return _secret
    try:
        value = json.loads(
            boto3.client("secretsmanager").get_secret_value(
                SecretId=os.environ["ONEMAP_SECRET_ARN"]
            )["SecretString"]
        )
        fields = [value.get(key, "") for key in ("email", "password", "access_token")]
        if not all(isinstance(field, str) for field in fields):
            raise ValueError
        _secret = (fields[0].strip(), fields[1], fields[2].strip())
        _secret_until = time.monotonic() + 60
        return _secret
    except (BotoCoreError, ClientError, KeyError, ValueError, AttributeError):
        logger.warning("Location search credentials unavailable")
        raise SearchUnavailable from None


client = OneMapClient(credentials=credentials)


def response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body),
    }


def error(status, code, message, details=None):
    return response(
        status,
        {"error": {"code": code, "message": message, "details": details or {}}},
    )


def handler(event, context):
    if event.get("rawPath") not in (
        "/api/v1/locations/search",
        "/api/v1/locations/search/",
    ):
        return error(404, "not_found", "This endpoint could not be found.")
    if event.get("requestContext", {}).get("http", {}).get("method") != "GET":
        return error(405, "method_not_allowed", "Use GET for location search.")
    # Parse the raw string so repeated q parameters cannot become a combined query.
    values = parse_qs(event.get("rawQueryString", ""), keep_blank_values=True)
    queries = values.get("q", [])
    query = queries[0].strip() if len(queries) == 1 else ""
    if not 2 <= len(query) <= 120 or any(
        ord(character) < 32 or ord(character) == 127 for character in query
    ):
        return error(
            400,
            "invalid",
            "Some fields are invalid.",
            {"q": ["Enter an address or postal code between 2 and 120 characters."]},
        )
    try:
        return response(200, {"results": client.search(query)})
    except (SearchUnavailable, SearchFailed, SearchTimeout) as exc:
        logger.warning("Location search failed: %s", exc.default_code)
        return error(exc.status_code, exc.default_code, str(exc.detail))
