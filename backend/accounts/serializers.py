from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    groups = serializers.SerializerMethodField()
    # Set once the marketplace has a Merchant model
    merchant = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "groups", "merchant"]

    def get_groups(self, user):
        # Cognito groups from the token; Django groups for session logins
        groups = getattr(user, "cognito_groups", None)
        if groups is None:
            groups = user.groups.values_list("name", flat=True)
        return sorted(groups)

    def get_merchant(self, user):
        return None
