import json
import logging
import os
import runpy
import tempfile
import time
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import jwt
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework.authentication import SessionAuthentication
from rest_framework.test import APITestCase
from rest_framework.views import APIView

from api import storage
from api.authentication import (
    PROXY_HEADERS,
    CognitoAuthentication,
    DevAuthentication,
    get_dev_user,
)
from api.local_files import local_file_urlpatterns, serve
from api.log_filters import RedactLocalFileTokens
from api.storage import StorageUnavailable, StoredObject
from config.dev_auth import authentication_classes, dev_auth_enabled

ISSUER = "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_test"
CLIENT_ID = "test-client"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(PRIVATE_KEY.public_key()))
JWKS = json.dumps({"keys": [{**JWK, "kid": "test-key", "alg": "RS256"}]})


def make_token(**overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": "11111111-2222-3333-4444-555555555555",
        "client_id": CLIENT_ID,
        "token_use": "access",
        "iat": now,
        "exp": now + 300,
        "email": "alice@example.com",
        "cognito:groups": ["owner"],
        **overrides,
    }
    return jwt.encode(claims, PRIVATE_KEY, "RS256", headers={"kid": "test-key"})


class HealthTests(APITestCase):
    def test_health_is_public(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)


@override_settings(
    COGNITO_ISSUER=ISSUER, COGNITO_CLIENT_ID=CLIENT_ID, COGNITO_JWKS=JWKS
)
class CognitoAuthenticationTests(APITestCase):
    def get_me(self, token):
        return self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_valid_token_creates_user(self):
        response = self.get_me(make_token())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "alice@example.com")
        self.assertEqual(response.json()["groups"], ["owner"])
        user = get_user_model().objects.get()
        self.assertEqual(user.cognito_sub, "11111111-2222-3333-4444-555555555555")

    def test_existing_user_is_reused_and_email_updated(self):
        self.get_me(make_token())
        response = self.get_me(make_token(email="new@example.com"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_user_model().objects.get().email, "new@example.com")

    def test_rejects_invalid_tokens(self):
        cases = {
            "expired": make_token(exp=int(time.time()) - 10),
            "other client": make_token(client_id="other"),
            "id token": make_token(token_use="id"),
            "other issuer": make_token(iss="https://example.com"),
            "garbage": "not-a-jwt",
        }
        for name, token in cases.items():
            with self.subTest(name):
                response = self.get_me(token)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(
                    response.json()["error"]["code"], "authentication_failed"
                )

    def test_rejects_token_signed_by_another_key(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode(
            jwt.decode(make_token(), options={"verify_signature": False}),
            other,
            "RS256",
            headers={"kid": "test-key"},
        )
        self.assertEqual(self.get_me(token).status_code, 401)

    def test_missing_token_is_401(self):
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 401)


# Storage (api.storage, api.local_files, api.log_filters)

PET_ID = "5d0c7a3e-1f2b-4c3d-8e9f-0a1b2c3d4e5f"
DOC_KEY = f"pets/{PET_ID}/documents/9a8b7c6d-5e4f-4a3b-9c2d-1e0f9a8b7c6d.pdf"


@override_settings(
    PET_FILES_BACKEND="s3",
    PET_FILES_BUCKET="test-bucket",
    PET_FILES_REGION="ap-southeast-1",
    PET_FILES_ENDPOINT_URL="",
)
class StorageS3Tests(TestCase):
    """The S3 backend against botocore's Stubber. Never touches the network."""

    def setUp(self):
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        # Drop AWS_PROFILE, AWS_SESSION_TOKEN, AWS_ENDPOINT_URL* and the like
        for name in [name for name in os.environ if name.startswith("AWS_")]:
            del os.environ[name]
        os.environ.update(
            {
                "AWS_ACCESS_KEY_ID": "testing",
                "AWS_SECRET_ACCESS_KEY": "testing",
                "AWS_CONFIG_FILE": os.devnull,
                "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
                "AWS_EC2_METADATA_DISABLED": "true",
                # Ignore a developer's legacy ~/.boto credentials too
                "BOTO_CONFIG": os.devnull,
            }
        )
        storage._s3_client.cache_clear()
        self.addCleanup(storage._s3_client.cache_clear)

    def s3_client(self):
        return storage._s3_client(
            settings.PET_FILES_REGION, settings.PET_FILES_ENDPOINT_URL
        )

    def stub(self):
        stubber = Stubber(self.s3_client())
        stubber.activate()
        self.addCleanup(stubber.deactivate)
        return stubber

    def test_presign_put_signs_type_and_length(self):
        url = storage.presign_put(
            DOC_KEY, content_type="application/pdf", size_bytes=1234
        )
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.netloc, "test-bucket.s3.ap-southeast-1.amazonaws.com")
        self.assertEqual(parts.path, f"/{DOC_KEY}")
        self.assertEqual(query["X-Amz-Algorithm"], ["AWS4-HMAC-SHA256"])
        self.assertEqual(
            query["X-Amz-SignedHeaders"], ["content-length;content-type;host"]
        )
        self.assertEqual(query["X-Amz-Expires"], ["900"])
        self.assertFalse([name for name in query if "checksum" in name.lower()])

    def test_presign_get_sets_response_headers(self):
        url = storage.presign_get(
            DOC_KEY,
            content_type="application/pdf",
            disposition='attachment; filename="pet-document.pdf"',
        )
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["response-content-type"], ["application/pdf"])
        self.assertEqual(
            query["response-content-disposition"],
            ['attachment; filename="pet-document.pdf"'],
        )
        self.assertEqual(query["response-cache-control"], ["private, no-store"])
        self.assertEqual(query["X-Amz-Expires"], ["300"])

    @override_settings(PET_FILES_ENDPOINT_URL="http://localhost:4566")
    def test_endpoint_override_uses_path_style(self):
        url = storage.presign_put(DOC_KEY, content_type="application/pdf", size_bytes=3)
        self.assertTrue(url.startswith("http://localhost:4566/test-bucket/"), url)

    def test_head_returns_stored_object(self):
        stubber = self.stub()
        stubber.add_response(
            "head_object",
            {"ContentLength": 3, "ContentType": "application/pdf"},
            {"Bucket": "test-bucket", "Key": DOC_KEY},
        )
        self.assertEqual(storage.head(DOC_KEY), StoredObject(3, "application/pdf"))
        stubber.assert_no_pending_responses()

    def test_head_missing_object_is_none(self):
        stubber = self.stub()
        stubber.add_client_error(
            "head_object", service_error_code="404", http_status_code=404
        )
        self.assertIsNone(storage.head(DOC_KEY))

    def test_head_forbidden_is_none_and_logged(self):
        stubber = self.stub()
        stubber.add_client_error(
            "head_object", service_error_code="403", http_status_code=403
        )
        with self.assertLogs("api.storage", "INFO") as logs:
            self.assertIsNone(storage.head(DOC_KEY))
        self.assertEqual(logs.output, ["INFO:api.storage:Pet file head returned 403"])

    def test_head_server_error_is_unavailable(self):
        stubber = self.stub()
        stubber.add_client_error(
            "head_object", service_error_code="500", http_status_code=500
        )
        with self.assertLogs("api.storage", "WARNING") as logs:
            with self.assertRaises(StorageUnavailable):
                storage.head(DOC_KEY)
        # Only the operation and the error code are logged, never the key
        self.assertEqual(logs.output, ["WARNING:api.storage:Pet file head failed: 500"])

    def test_head_connection_error_is_unavailable(self):
        error = EndpointConnectionError(endpoint_url="https://test-bucket.s3.test")
        with (
            mock.patch.object(self.s3_client(), "head_object", side_effect=error),
            self.assertLogs("api.storage", "WARNING") as logs,
            self.assertRaises(StorageUnavailable),
        ):
            storage.head(DOC_KEY)
        self.assertEqual(
            logs.output,
            ["WARNING:api.storage:Pet file head failed: EndpointConnectionError"],
        )

    def test_delete(self):
        stubber = self.stub()
        stubber.add_response(
            "delete_object", {}, {"Bucket": "test-bucket", "Key": DOC_KEY}
        )
        self.assertIsNone(storage.delete(DOC_KEY))
        stubber.assert_no_pending_responses()

    def test_delete_missing_object_is_ignored(self):
        stubber = self.stub()
        stubber.add_client_error(
            "delete_object", service_error_code="NoSuchKey", http_status_code=404
        )
        self.assertIsNone(storage.delete(DOC_KEY))

    def test_delete_server_error_is_unavailable(self):
        stubber = self.stub()
        stubber.add_client_error(
            "delete_object", service_error_code="500", http_status_code=500
        )
        with (
            self.assertLogs("api.storage", "WARNING") as logs,
            self.assertRaises(StorageUnavailable),
        ):
            storage.delete(DOC_KEY)
        self.assertEqual(
            logs.output, ["WARNING:api.storage:Pet file delete failed: 500"]
        )

    def test_missing_credentials_make_presigning_unavailable(self):
        del os.environ["AWS_ACCESS_KEY_ID"]
        del os.environ["AWS_SECRET_ACCESS_KEY"]
        storage._s3_client.cache_clear()
        with self.assertLogs("api.storage", "WARNING") as logs:
            with self.assertRaises(StorageUnavailable):
                storage.presign_put(
                    DOC_KEY, content_type="application/pdf", size_bytes=3
                )
            with self.assertRaises(StorageUnavailable):
                storage.presign_get(
                    DOC_KEY, content_type="application/pdf", disposition="inline"
                )
        self.assertEqual(
            logs.output,
            [
                "WARNING:api.storage:Pet file presign_put failed: NoCredentialsError",
                "WARNING:api.storage:Pet file presign_get failed: NoCredentialsError",
            ],
        )

    def test_delete_on_commit_never_raises(self):
        with (
            mock.patch("api.storage.delete", side_effect=StorageUnavailable) as delete,
            self.assertLogs("api.storage", "WARNING") as logs,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                storage.delete_on_commit(DOC_KEY, "", "pets/x/photos/y.jpg")
        delete.assert_has_calls([mock.call(DOC_KEY), mock.call("pets/x/photos/y.jpg")])
        self.assertEqual(delete.call_count, 2)
        self.assertEqual(
            logs.output,
            ["WARNING:api.storage:Pet file cleanup failed: StorageUnavailable"] * 2,
        )

    def test_disabled_backend_is_unavailable(self):
        with override_settings(PET_FILES_BACKEND="disabled"):
            with self.assertRaises(StorageUnavailable):
                storage.presign_put(
                    DOC_KEY, content_type="application/pdf", size_bytes=3
                )
            with self.assertRaises(StorageUnavailable):
                storage.head(DOC_KEY)

    def test_unknown_backend_is_improperly_configured(self):
        with (
            override_settings(PET_FILES_BACKEND="ftp"),
            self.assertRaises(ImproperlyConfigured),
        ):
            storage.head(DOC_KEY)

    def test_validate_key(self):
        self.assertEqual(storage.validate_key(DOC_KEY), DOC_KEY)
        for key in ["../x", "/abs", "a//b", "a/./b", "a/../b", "", "a" * 513]:
            with self.subTest(key=key[:20]), self.assertRaises(ValueError):
                storage.validate_key(key)


class LocalStorageTests(SimpleTestCase):
    """The local backend and its signed URL view, in a temporary folder."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        # Storage lives one level down, so "outside the root" is still in tmp
        self.root = self.tmp / "storage"
        self.enterContext(
            override_settings(
                PET_FILES_BACKEND="local",
                PET_FILES_LOCAL_DIR=str(self.root),
                PET_FILES_LOCAL_URL="http://testserver/api/v1/local-files/",
            )
        )
        self.factory = RequestFactory()

    @staticmethod
    def token_of(url):
        prefix = "http://testserver/api/v1/local-files/"
        assert url.startswith(prefix) and url.endswith("/"), url
        return url.removeprefix(prefix).removesuffix("/")

    def put(self, token, body, content_type="application/pdf", **extra):
        request = self.factory.put(
            f"/api/v1/local-files/{token}/",
            data=body,
            content_type=content_type,
            **extra,
        )
        return serve(request, token)

    def get(self, token, **extra):
        request = self.factory.get(f"/api/v1/local-files/{token}/", **extra)
        response = serve(request, token)
        if response.streaming:
            body = b"".join(response.streaming_content)
        else:
            body = response.content
        response.close()
        return response, body

    def put_token(self, key=DOC_KEY, size=3, content_type="application/pdf"):
        url = storage.presign_put(key, content_type=content_type, size_bytes=size)
        return self.token_of(url)

    def get_token(self, key=DOC_KEY):
        url = storage.presign_get(
            key,
            content_type="application/pdf",
            disposition='attachment; filename="pet-document.pdf"',
        )
        return self.token_of(url)

    def stored_files(self):
        return sorted(p for p in self.tmp.rglob("*") if p.is_file())

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        self.assertEqual(json.loads(response.content)["error"]["code"], code)

    def test_put_stores_file_and_metadata(self):
        response = self.put(self.put_token(), b"%PD")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(storage.head(DOC_KEY), StoredObject(3, "application/pdf"))
        self.assertEqual((self.root / DOC_KEY).read_bytes(), b"%PD")
        # Only the file and its sidecar; no temporary files are left behind
        self.assertEqual(
            self.stored_files(),
            [self.root / DOC_KEY, self.root / f"{DOC_KEY}.meta"],
        )

    def test_put_rejects_what_the_token_does_not_allow(self):
        put_token = self.put_token()
        tampered = put_token[:-1] + ("A" if put_token[-1] != "A" else "B")
        cases = {
            "wrong content type": lambda: self.put(put_token, b"abc", "image/png"),
            "wrong length": lambda: self.put(put_token, b"abcd"),
            "tampered token": lambda: self.put(tampered, b"abc"),
            "GET token used for PUT": lambda: self.put(self.get_token(), b"abc"),
        }
        for name, send in cases.items():
            with self.subTest(name):
                self.assert_error(send(), 403, "signature_mismatch")
                self.assertIsNone(storage.head(DOC_KEY))
                self.assertEqual(self.stored_files(), [])

    def test_expired_token(self):
        token = self.put_token()
        with mock.patch("api.local_files.time.time", return_value=time.time() + 901):
            response = self.put(token, b"abc")
        self.assert_error(response, 403, "expired")
        self.assertEqual(self.stored_files(), [])

    def test_forged_token_cannot_escape_the_storage_folder(self):
        far_future = int(time.time()) + 3600
        payloads = {
            "relative key": {"k": "../outside.pdf"},
            "traversal under pets/": {"k": "pets/../../outside.pdf"},
            "absolute key": {"k": str(self.tmp / "outside.pdf")},
            "no key": {},
            "key not a string": {"k": ["pets", "x.pdf"]},
        }
        for name, extra in payloads.items():
            with self.subTest(name):
                payload = {
                    "m": "PUT",
                    "ct": "application/pdf",
                    "n": 3,
                    "exp": far_future,
                    **extra,
                }
                token = signing.dumps(payload, salt="api.local_files", compress=True)
                self.assert_error(self.put(token, b"abc"), 403, "signature_mismatch")
                self.assertFalse((self.tmp / "outside.pdf").exists())
                self.assertEqual(self.stored_files(), [])

    def test_only_loopback_clients_are_served(self):
        response = self.put(self.put_token(), b"abc", REMOTE_ADDR="192.168.1.20")
        self.assert_error(response, 403, "forbidden")
        self.assertEqual(self.stored_files(), [])

    def test_route_is_off_unless_the_local_backend_is_active(self):
        token = self.put_token()
        with override_settings(PET_FILES_BACKEND="s3"):
            self.assert_error(self.put(token, b"abc"), 404, "not_found")
        self.assertEqual(self.stored_files(), [])

    def test_get_serves_bytes_with_signed_headers(self):
        self.assertEqual(self.put(self.put_token(), b"%PD").status_code, 200)
        response, body = self.get(self.get_token())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body, b"%PD")
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="pet-document.pdf"'
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_get_missing_file_is_404(self):
        response, body = self.get(self.get_token())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(body)["error"]["code"], "not_found")

    def test_delete_removes_file_and_metadata(self):
        self.assertEqual(self.put(self.put_token(), b"%PD").status_code, 200)
        storage.delete(DOC_KEY)
        self.assertIsNone(storage.head(DOC_KEY))
        self.assertEqual(self.stored_files(), [])
        storage.delete(DOC_KEY)  # idempotent

    def test_serve_is_csrf_exempt(self):
        self.assertIs(serve.csrf_exempt, True)

    def test_local_file_urlpatterns(self):
        for backend in ["s3", "disabled"]:
            with self.subTest(backend), override_settings(PET_FILES_BACKEND=backend):
                self.assertEqual(local_file_urlpatterns(), [])
        patterns = local_file_urlpatterns()
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].name, "local-file")

    def test_route_matches_without_the_trailing_slash(self):
        # Otherwise CommonMiddleware answers 301, or 500 for a PUT, and logs the token
        (pattern,) = local_file_urlpatterns()
        token = self.put_token()
        for path in [f"api/v1/local-files/{token}/", f"api/v1/local-files/{token}"]:
            with self.subTest(slash=path.endswith("/")):
                match = pattern.resolve(path)
                self.assertIs(match.func, serve)
                self.assertEqual(match.kwargs, {"token": token})
        match = pattern.resolve(f"api/v1/local-files/{token}")
        request = self.factory.put(
            f"/api/v1/local-files/{token}", data=b"%PD", content_type="application/pdf"
        )
        self.assertEqual(match.func(request, **match.kwargs).status_code, 200)
        self.assertEqual(storage.head(DOC_KEY), StoredObject(3, "application/pdf"))


class LogFilterTests(SimpleTestCase):
    def make_record(self, msg, args):
        return logging.LogRecord(
            "django.server", logging.INFO, __file__, 1, msg, args, None
        )

    def test_redacts_local_file_tokens(self):
        record = self.make_record(
            '"%s" %s %s', ("PUT /api/v1/local-files/abc.DEF:ghi/ HTTP/1.1", "200", "0")
        )
        self.assertTrue(RedactLocalFileTokens().filter(record))
        message = record.getMessage()
        self.assertIn("/local-files/<redacted>/", message)
        self.assertNotIn("abc.DEF", message)
        self.assertEqual(
            message, '"PUT /api/v1/local-files/<redacted>/ HTTP/1.1" 200 0'
        )

    def test_redacts_tokens_without_a_trailing_slash(self):
        record = self.make_record(
            '"%s" %s %s', ("GET /api/v1/local-files/abc.DEF:ghi HTTP/1.1", "301", "0")
        )
        self.assertTrue(RedactLocalFileTokens().filter(record))
        self.assertEqual(
            record.getMessage(), '"GET /api/v1/local-files/<redacted> HTTP/1.1" 301 0'
        )

    def test_leaves_other_records_unchanged(self):
        args = ("GET /api/v1/health/ HTTP/1.1", "200", "15")
        record = self.make_record('"%s" %s %s', args)
        self.assertTrue(RedactLocalFileTokens().filter(record))
        self.assertEqual(record.msg, '"%s" %s %s')
        self.assertEqual(record.args, args)


class S3LoggingSettingTests(SimpleTestCase):
    def test_s3_backend_logs_storage_info(self):
        # config/settings.py again, with the bucket set as in Lambda
        with mock.patch.dict(os.environ, {"PET_FILES_BUCKET": "test-bucket"}):
            values = runpy.run_path(str(settings.BASE_DIR / "config" / "settings.py"))
        self.assertEqual(values["PET_FILES_BACKEND"], "s3")
        # A level only: no handler, so records reach Lambda's root handler once
        self.assertEqual(
            values["LOGGING"],
            {
                "version": 1,
                "disable_existing_loggers": False,
                "loggers": {"api.storage": {"level": "INFO"}},
            },
        )


# Dev auth (config.dev_auth, api.authentication.DevAuthentication)

COGNITO = "api.authentication.CognitoAuthentication"
DEV = "api.authentication.DevAuthentication"
SESSION = "rest_framework.authentication.SessionAuthentication"


class DevAuthSettingTests(SimpleTestCase):
    def test_dev_auth_enabled(self):
        self.assertIs(dev_auth_enabled({"DJANGO_DEV_AUTH": "true"}, True), True)
        self.assertIs(dev_auth_enabled({"DJANGO_DEV_AUTH": " TRUE "}, True), True)
        self.assertIs(dev_auth_enabled({"DJANGO_DEV_AUTH": "true"}, False), False)
        self.assertIs(dev_auth_enabled({}, True), False)
        self.assertIs(dev_auth_enabled({"DJANGO_DEV_AUTH": "false"}, True), False)
        self.assertIs(dev_auth_enabled({"DJANGO_DEV_AUTH": "1"}, True), False)

    def test_opt_in_inside_lambda_raises(self):
        environ = {"DJANGO_DEV_AUTH": "true", "AWS_LAMBDA_FUNCTION_NAME": "api"}
        for debug in [True, False]:
            with self.subTest(debug=debug), self.assertRaises(ImproperlyConfigured):
                dev_auth_enabled(environ, debug)

    def test_lambda_without_opt_in_is_fine(self):
        self.assertIs(
            dev_auth_enabled({"AWS_LAMBDA_FUNCTION_NAME": "api"}, True), False
        )

    def test_authentication_classes(self):
        self.assertEqual(authentication_classes(True), [COGNITO, DEV, SESSION])
        self.assertEqual(authentication_classes(False), [COGNITO, SESSION])


@override_settings(ALLOWED_HOSTS=["localhost", "testserver", "demo.ngrok.app"])
class DevAuthenticationTests(APITestCase):
    # override_settings(REST_FRAMEWORK=...) cannot work here: DRF binds
    # APIView.authentication_classes at import. Each test patches it instead.
    ALL = (CognitoAuthentication, DevAuthentication, SessionAuthentication)
    WITHOUT_DEV = (CognitoAuthentication, SessionAuthentication)

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = "localhost:8000"

    def use_classes(self, *classes):
        patcher = mock.patch.object(APIView, "authentication_classes", list(classes))
        patcher.start()
        self.addCleanup(patcher.stop)

    def enable(self, enabled=True):
        self.enterContext(override_settings(DEV_AUTH_ENABLED=enabled))

    def get_me(self, authorization, **extra):
        return self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=authorization, **extra)

    def assert_401(self, response, code):
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], code)

    def test_dev_alice_signs_in_and_is_reused(self):
        self.use_classes(*self.ALL)
        self.enable()
        response = self.get_me("Dev alice")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "alice@dev.petstop.test")
        self.assertEqual(response.json()["groups"], ["owner"])
        user = get_user_model().objects.get()
        self.assertEqual(user.cognito_sub, "dev:alice")
        self.assertEqual(user.username, "dev-alice")

        self.assertEqual(self.get_me("Dev alice").status_code, 200)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_merchant_and_case_insensitive_handle(self):
        self.use_classes(*self.ALL)
        self.enable()
        response = self.get_me("Dev mira")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["groups"], ["merchant"])
        response = self.get_me("Dev ALICE")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "alice@dev.petstop.test")

    def test_malformed_or_unknown_handle_fails(self):
        self.use_classes(*self.ALL)
        self.enable()
        for header in ["Dev nobody", "Dev", "Dev a b"]:
            with self.subTest(header):
                self.assert_401(self.get_me(header), "authentication_failed")
        self.assertFalse(get_user_model().objects.exists())

    def test_inactive_dev_user_fails(self):
        self.use_classes(*self.ALL)
        self.enable()
        user = get_dev_user("bob")
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assert_401(self.get_me("Dev bob"), "authentication_failed")

    def test_listed_but_disabled_is_ignored(self):
        self.use_classes(*self.ALL)
        self.enable(False)
        self.assert_401(self.get_me("Dev alice"), "not_authenticated")
        self.assertFalse(get_user_model().objects.exists())

    def test_not_listed_is_ignored(self):
        self.use_classes(*self.WITHOUT_DEV)
        self.enable()
        response = self.get_me("Dev alice")
        self.assert_401(response, "not_authenticated")
        # Cognito stays first, so the challenge is unchanged
        self.assertEqual(response["WWW-Authenticate"], 'Bearer realm="api"')

    def test_non_loopback_requests_are_ignored(self):
        self.use_classes(*self.ALL)
        self.enable()
        cases = {
            "foreign host": {"HTTP_HOST": "demo.ngrok.app"},
            "foreign peer": {"REMOTE_ADDR": "192.168.1.20"},
        }
        for name, extra in cases.items():
            with self.subTest(name):
                self.assert_401(self.get_me("Dev alice", **extra), "not_authenticated")
        self.assertFalse(get_user_model().objects.exists())

    def test_proxied_requests_are_ignored(self):
        # A Host-rewriting tunnel (ngrok --host-header=rewrite) connects from
        # loopback with Host localhost, but adds a forwarding header
        self.use_classes(*self.ALL)
        self.enable()
        for header in PROXY_HEADERS:
            with self.subTest(header):
                response = self.get_me(
                    "Dev alice",
                    HTTP_HOST="localhost",
                    REMOTE_ADDR="127.0.0.1",
                    **{header: "203.0.113.9"},
                )
                self.assert_401(response, "not_authenticated")
        self.assertFalse(get_user_model().objects.exists())

    def test_ipv6_loopback_host_is_accepted(self):
        self.use_classes(*self.ALL)
        self.enable()
        with override_settings(ALLOWED_HOSTS=["[::1]"]):
            response = self.get_me(
                "Dev alice", HTTP_HOST="[::1]:8000", REMOTE_ADDR="::1"
            )
        self.assertEqual(response.status_code, 200)
