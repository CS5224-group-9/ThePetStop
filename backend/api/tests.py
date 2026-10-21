import json
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

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
