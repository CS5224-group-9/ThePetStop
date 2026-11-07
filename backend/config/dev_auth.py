"""Local development sign-in switch (`Authorization: Dev <handle>`).

Imports nothing from DRF or the apps, so settings.py can import it. The scheme
itself is `api.authentication.DevAuthentication`.
"""

from django.core.exceptions import ImproperlyConfigured

OPT_IN = "DJANGO_DEV_AUTH"


def dev_auth_enabled(environ, debug: bool) -> bool:
    """True only with DEBUG, an explicit opt-in, and outside AWS Lambda.

    An opt-in inside Lambda raises, so a misconfigured function fails to start
    rather than run with dev sign-in.
    """
    opted_in = environ.get(OPT_IN, "").strip().lower() == "true"
    if opted_in and "AWS_LAMBDA_FUNCTION_NAME" in environ:
        raise ImproperlyConfigured("DJANGO_DEV_AUTH must never be set in AWS Lambda.")
    return opted_in and debug


def authentication_classes(enabled: bool) -> list[str]:
    """DRF DEFAULT_AUTHENTICATION_CLASSES. Cognito stays first, so a missing
    login gets 401 (its authenticate_header) rather than 403."""
    return [
        "api.authentication.CognitoAuthentication",
        *(["api.authentication.DevAuthentication"] if enabled else []),
        "rest_framework.authentication.SessionAuthentication",
    ]
