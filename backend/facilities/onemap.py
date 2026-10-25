"""Bounded OneMap search requests; credentials and tokens never reach the browser."""

import json
import math
import re
import time
from http.client import HTTPException, HTTPSConnection
from threading import Lock
from urllib.parse import urlencode

from django.conf import settings
from rest_framework.exceptions import APIException


class SearchUnavailable(APIException):
    status_code = 503
    default_code = "location_search_unavailable"
    default_detail = "Location search is unavailable. Please try again later."


class SearchFailed(APIException):
    status_code = 502
    default_code = "location_search_failed"
    default_detail = "Location search could not be completed. Please try again."


class SearchTimeout(APIException):
    status_code = 504
    default_code = "location_search_timeout"
    default_detail = "Location search timed out. Please try again."


class _TokenRejected(Exception):
    pass


def _request_json(path, *, token=None, credentials=None):
    # The upstream host is fixed. Redirects are not followed or user-controlled.
    connection = HTTPSConnection("www.onemap.gov.sg", timeout=4)
    headers = {"Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = token
    if credentials:
        headers["Content-Type"] = "application/json"
        body = json.dumps(credentials)
    try:
        connection.request("POST" if credentials else "GET", path, body, headers)
        response = connection.getresponse()
        if response.status in (401, 403):
            raise _TokenRejected
        if response.status != 200:
            raise SearchUnavailable
        payload = response.read(1_000_001)
        if len(payload) > 1_000_000:
            raise SearchFailed
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise SearchFailed
        return data
    except TimeoutError:
        raise SearchTimeout from None
    except (OSError, HTTPException):
        raise SearchUnavailable from None
    except (ValueError, UnicodeError):
        raise SearchFailed from None
    finally:
        connection.close()


class OneMapClient:
    def __init__(self):
        self._lock = Lock()
        self._token = None
        self._expires = 0
        self._configuration = None
        self._supplied_used = False

    def _get_token(self, *, rejected=None):
        email = settings.ONEMAP_EMAIL.strip()
        password = settings.ONEMAP_PASSWORD
        supplied = settings.ONEMAP_ACCESS_TOKEN.strip()
        with self._lock:
            configuration = (supplied, email, password)
            if self._configuration != configuration:
                self._token, self._expires = None, 0
                self._supplied_used = False
                self._configuration = configuration
            if (
                self._token
                and self._token != rejected
                and (self._expires is None or self._expires > time.time())
            ):
                return self._token
            # An externally supplied token has no trusted expiry metadata. Use it
            # until OneMap rejects it, then renew once instead of reusing it.
            self._token = None
            if supplied and not self._supplied_used:
                self._supplied_used = True
                if any(
                    ord(character) < 32 or ord(character) == 127
                    for character in supplied
                ):
                    raise SearchUnavailable
                self._token, self._expires = supplied, None
                return supplied
            if not email or not password:
                raise SearchUnavailable
            try:
                data = _request_json(
                    "/api/auth/post/getToken",
                    credentials={"email": email, "password": password},
                )
                token = data.get("access_token")
                expires = float(data.get("expiry_timestamp", 0))
                if (
                    not isinstance(token, str)
                    or not token
                    or "\r" in token
                    or "\n" in token
                    or not math.isfinite(expires)
                    or expires <= time.time()
                ):
                    raise SearchUnavailable
            except (_TokenRejected, TypeError, ValueError):
                raise SearchUnavailable from None
            self._token, self._expires = token, expires
            return token

    def search(self, query):
        path = "/api/common/elastic/search?" + urlencode(
            {"searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1}
        )
        token = self._get_token()
        for attempt in range(2):
            try:
                data = _request_json(path, token=token)
                # OneMap also reports expired/invalid tokens in a 200 response.
                if "error" in data:
                    raise _TokenRejected
                break
            except _TokenRejected:
                if attempt:
                    raise SearchUnavailable from None
                token = self._get_token(rejected=token)
        rows = data.get("results")
        if not isinstance(rows, list):
            raise SearchFailed
        results = []
        seen = set()
        for row in rows[:100]:
            if not isinstance(row, dict):
                continue
            try:
                lat, lng = float(row["LATITUDE"]), float(row["LONGITUDE"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (1.15 <= lat <= 1.5 and 103.55 <= lng <= 104.15):
                continue
            label = row.get("ADDRESS") or row.get("SEARCHVAL")
            if not isinstance(label, str) or not label.strip() or label == "NIL":
                continue
            label = label.strip()[:500]
            key = (label, lat, lng)
            if key in seen:
                continue
            seen.add(key)
            postal = row.get("POSTAL")
            results.append(
                {
                    "label": label,
                    "postal_code": postal
                    if isinstance(postal, str) and re.fullmatch(r"\d{6}", postal)
                    else None,
                    "latitude": lat,
                    "longitude": lng,
                }
            )
            if len(results) == 10:
                break
        if rows and not results:
            raise SearchFailed
        return results


client = OneMapClient()
