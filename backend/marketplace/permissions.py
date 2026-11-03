from rest_framework.permissions import BasePermission

from .models import Merchant


class IsMerchant(BasePermission):
    """Allow access when the user owns an active merchant shop."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and Merchant.objects.filter(owner=user, active=True).exists()
        )
