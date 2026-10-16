from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Return every API error as {"error": {"code", "message", "details"}}."""
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, exceptions.ValidationError):
        code, message, details = "invalid", "Some fields are invalid.", response.data
    else:
        code, message, details = exc.default_code, str(exc.detail), {}
    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
