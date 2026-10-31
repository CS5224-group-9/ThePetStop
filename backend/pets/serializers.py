from rest_framework import serializers
from .models import pet

class PetSerializers(serializers.ModelSerializer):
    class Meta:
        model = pet
        fields = [
            "id",
            "name",
            "species",
            "breeds",
            "sex",
            "date_of_birth",
            "microchip_no",
            "photo_key",
            "allergies",
            "diet_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields=["id",
            "created_at",
            "updated_at"]
