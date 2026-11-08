import json
import os
import time
from unittest import TestCase
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from facilities import search_handler
from facilities.onemap import (
    OneMapClient,
    SearchFailed,
    SearchTimeout,
    SearchUnavailable,
)


def event(query="q=Bukit+Batok+MRT", method="GET"):
    return {
        "rawPath": "/api/v1/locations/search/",
        "requestContext": {"http": {"method": method}},
        "rawQueryString": query,
    }


class SearchHandlerTests(TestCase):
    @patch.object(search_handler.client, "search", return_value=[])
    def test_public_request_needs_no_authentication(self, search):
        result = search_handler.handler(event(), None)
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(json.loads(result["body"]), {"results": []})
        self.assertEqual(result["headers"]["Cache-Control"], "no-store")
        search.assert_called_once_with("Bukit Batok MRT")

    @patch.object(search_handler.client, "search")
    def test_invalid_queries_never_reach_onemap(self, search):
        for query in ("", "q=", "q=a", "q=" + "a" * 121, "q=ab%00cd", "q=ab&q=cd"):
            with self.subTest(query=query):
                result = search_handler.handler(event(query), None)
                self.assertEqual(result["statusCode"], 400)
                self.assertEqual(json.loads(result["body"])["error"]["code"], "invalid")
        search.assert_not_called()
        self.assertEqual(
            search_handler.handler(event(method="POST"), None)["statusCode"], 405
        )

    @patch.object(search_handler.client, "search")
    def test_other_location_paths_are_not_served(self, search):
        request = event()
        request["rawPath"] = "/api/v1/locations/private/"
        self.assertEqual(search_handler.handler(request, None)["statusCode"], 404)
        search.assert_not_called()

    @patch.object(search_handler.client, "search")
    def test_upstream_errors_never_become_session_errors(self, search):
        for exception in (SearchUnavailable, SearchFailed, SearchTimeout):
            with self.subTest(exception=exception):
                search.side_effect = exception()
                result = search_handler.handler(event(), None)
                self.assertEqual(result["statusCode"], exception.status_code)
                self.assertEqual(
                    json.loads(result["body"])["error"]["code"], exception.default_code
                )

    @patch.dict(os.environ, {"ONEMAP_SECRET_ARN": "test-secret"})
    @patch.object(search_handler, "_secret", None)
    @patch("facilities.search_handler.boto3.client")
    def test_secret_is_cached_and_reloaded_after_rotation(self, aws):
        secret = aws.return_value.get_secret_value
        secret.side_effect = [
            {
                "SecretString": json.dumps(
                    {"email": "owner@example.test", "password": value}
                )
            }
            for value in ("original", "rotated")
        ]
        self.assertEqual(search_handler.credentials()[1], "original")
        self.assertEqual(search_handler.credentials()[1], "original")
        secret.assert_called_once_with(SecretId="test-secret")
        with patch.object(search_handler, "_secret_until", 0):
            self.assertEqual(search_handler.credentials()[1], "rotated")

    @patch.dict(os.environ, {"ONEMAP_SECRET_ARN": "test-secret"})
    @patch.object(search_handler, "_secret", None)
    @patch("facilities.search_handler.boto3.client")
    def test_secret_errors_are_safe_service_errors(self, aws):
        secret = aws.return_value.get_secret_value
        for failure in (
            {"SecretString": "not-json"},
            {"SecretString": "[]"},
            {"SecretString": '{"password": null}'},
            ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "private"}},
                "GetSecretValue",
            ),
        ):
            secret.side_effect = failure if isinstance(failure, Exception) else None
            secret.return_value = failure
            with self.assertRaises(SearchUnavailable):
                search_handler.credentials()

    @patch("facilities.onemap._request_json")
    def test_injected_credentials_refresh_rejected_token(self, request):
        from facilities.onemap import _TokenRejected

        credentials = Mock(return_value=("owner@example.test", "password", ""))
        client = OneMapClient(credentials=credentials)
        request.side_effect = [
            {"access_token": "first", "expiry_timestamp": time.time() + 3600},
            _TokenRejected(),
            {"access_token": "second", "expiry_timestamp": time.time() + 3600},
            {"results": []},
        ]
        self.assertEqual(client.search("Bukit Batok"), [])
        self.assertEqual(request.call_args.kwargs["token"], "second")
