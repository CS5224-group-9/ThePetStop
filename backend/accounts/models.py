from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    # Blank for users not created through Cognito, such as a local superuser
    cognito_sub = models.CharField(max_length=64, blank=True)
    display_name = models.CharField(max_length=150, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cognito_sub"],
                condition=~Q(cognito_sub=""),
                name="unique_cognito_sub",
            )
        ]
