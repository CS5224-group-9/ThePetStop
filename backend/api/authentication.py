from functools import cache

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

# Cognito's token_use claim: "access" for access tokens, "id" for ID tokens
ACCESS_USE = "access"


@cache
def _jwks(issuer, jwks_json):
    # The Lambda has no internet access, so in AWS the keys arrive in COGNITO_JWKS.
    # Locally they are fetched from the user pool.
    if jwks_json:
        return jwt.PyJWKSet.from_json(jwks_json)
    return jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json").get_jwk_set()


def _signing_key(token):
    kid = jwt.get_unverified_header(token).get("kid")
    for key in _jwks(settings.COGNITO_ISSUER, settings.COGNITO_JWKS).keys:
        if key.key_id == kid:
            return key.key
    raise jwt.InvalidTokenError("Unknown signing key.")


def verify_access_token(token):
    """Return the claims of a valid Cognito access token for this app client."""
    claims = jwt.decode(
        token,
        _signing_key(token),
        algorithms=["RS256"],
        issuer=settings.COGNITO_ISSUER,
        options={"require": ["exp", "iat", "sub", "token_use", "client_id"]},
    )
    if claims["token_use"] != ACCESS_USE:
        raise jwt.InvalidTokenError("Not an access token.")
    if claims["client_id"] != settings.COGNITO_CLIENT_ID:
        raise jwt.InvalidTokenError("Token is for another client.")
    return claims


class CognitoAuthentication(BaseAuthentication):
    """Authenticate `Authorization: Bearer <Cognito access token>`.

    Maps the token's `sub` to `accounts.User`, creating it on first sign-in, and
    exposes the token's groups as `request.user.cognito_groups`.
    """

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b"bearer":
            return None
        if len(header) != 2 or not settings.COGNITO_ISSUER:
            raise exceptions.AuthenticationFailed("Invalid token.")
        try:
            claims = verify_access_token(header[1].decode())
        except (jwt.PyJWTError, UnicodeDecodeError) as exc:
            raise exceptions.AuthenticationFailed("Invalid token.") from exc

        user, _ = get_user_model().objects.get_or_create(
            cognito_sub=claims["sub"],
            defaults={"username": claims["sub"], "email": claims.get("email", "")},
        )
        if not user.is_active:
            raise exceptions.AuthenticationFailed("User inactive or deleted.")
        email = claims.get("email")
        if email and email != user.email:
            user.email = email
            user.save(update_fields=["email"])
        user.cognito_groups = claims.get("cognito:groups", [])
        return user, claims

    def authenticate_header(self, request):
        # Makes DRF answer a missing login with 401 rather than 403
        return 'Bearer realm="api"'
