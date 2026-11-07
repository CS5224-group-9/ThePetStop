from functools import cache

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http.request import split_domain_port
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

# Cognito's token_use claim: "access" for access tokens, "id" for ID tokens
ACCESS_USE = "access"

# Local development sign-in (DevAuthentication) and the local file route accept
# requests from this computer only
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
LOOPBACK_ADDRS = {"127.0.0.1", "::1"}
# Tunnels and reverse proxies add at least one of these
PROXY_HEADERS = (
    "HTTP_X_FORWARDED_FOR",
    "HTTP_X_FORWARDED_HOST",
    "HTTP_FORWARDED",
    "HTTP_X_REAL_IP",
    "HTTP_CF_CONNECTING_IP",
    "HTTP_TRUE_CLIENT_IP",
)

DEV_USERS = {
    "alice": {
        "email": "alice@dev.petstop.test",
        "display_name": "Alice (dev owner)",
        "groups": ["owner"],
    },
    "bob": {
        "email": "bob@dev.petstop.test",
        "display_name": "Bob (dev owner)",
        "groups": ["owner"],
    },
    "mira": {
        "email": "mira@dev.petstop.test",
        "display_name": "Mira (dev merchant)",
        "groups": ["merchant"],
    },
}


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


def get_dev_user(handle: str):
    """Get or create the local dev user. Its cognito_sub "dev:<handle>" can never
    match a Cognito UUID sub."""
    info = DEV_USERS[handle]
    user, _ = get_user_model().objects.get_or_create(
        cognito_sub=f"dev:{handle}",
        defaults={
            "username": f"dev-{handle}",
            "email": info["email"],
            "display_name": info["display_name"],
        },
    )
    return user


def is_loopback_request(request) -> bool:
    """Host is a loopback name, the peer address is loopback and no proxy header is
    present. A LAN peer can forge the Host header but not REMOTE_ADDR. A tunnel or
    reverse proxy on this computer connects from loopback and may rewrite Host to
    localhost, but it adds a forwarding header."""
    # CommonMiddleware has already validated the Host against ALLOWED_HOSTS
    host, _port = split_domain_port(request.get_host())
    return (
        host in LOOPBACK_HOSTS
        and request.META.get("REMOTE_ADDR") in LOOPBACK_ADDRS
        and not any(header in request.META for header in PROXY_HEADERS)
    )


class DevAuthentication(BaseAuthentication):
    """LOCAL ONLY: `Authorization: Dev <handle>`. Listed in settings only when
    DEV_AUTH_ENABLED (DEBUG, DJANGO_DEV_AUTH=true and not in AWS Lambda).

    The header carries no secret, so it is also ignored unless the request comes
    from this computer (a tunnel or `runserver 0.0.0.0` must not accept it).
    """

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b"dev":
            return None
        # Defence in depth: settings list this class only when enabled
        if not settings.DEV_AUTH_ENABLED or not is_loopback_request(request):
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("Invalid credentials.")
        handle = header[1].decode(errors="replace").lower()
        if handle not in DEV_USERS:
            raise exceptions.AuthenticationFailed("Invalid credentials.")
        user = get_dev_user(handle)
        if not user.is_active:
            raise exceptions.AuthenticationFailed("User inactive or deleted.")
        # Transient, like the Cognito token's groups
        user.cognito_groups = list(DEV_USERS[handle]["groups"])
        return user, None

    def authenticate_header(self, request):
        return 'Dev realm="api"'
