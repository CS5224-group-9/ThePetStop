import math

from rest_framework import serializers

from .animals import ANIMAL_COLUMNS
from .models import Facility


class FacilitySerializer(serializers.ModelSerializer):
    verification_status = serializers.SerializerMethodField()

    class Meta:
        model = Facility
        fields = (
            "id",
            "facility_type",
            "name",
            "address",
            "postal_code",
            "approved_animals",
            "latitude",
            "longitude",
            "licence_no",
            "phone",
            "website",
            "source",
            "source_url",
            "last_checked_at",
            "verification_status",
        )

    def get_verification_status(self, facility):
        return "verified" if facility.last_checked_at else "unverified"


class LocationSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=120, trim_whitespace=True)

    def validate_q(self, value):
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise serializers.ValidationError("Enter an address or postal code.")
        return value


class FacilityQuerySerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=Facility.Type.choices, required=False)
    animal = serializers.ChoiceField(
        choices=tuple(ANIMAL_COLUMNS.values()), required=False
    )
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lng = serializers.FloatField(min_value=-180, max_value=180, required=False)
    radius_km = serializers.FloatField(
        min_value=0.000001, max_value=100, required=False
    )

    def validate(self, attrs):
        if any(
            not math.isfinite(value)
            for key, value in attrs.items()
            if key in {"lat", "lng", "radius_km"}
        ):
            raise serializers.ValidationError(
                "Coordinates and radius must be finite numbers."
            )
        if ("lat" in attrs) != ("lng" in attrs) or (
            "radius_km" in attrs and "lat" not in attrs
        ):
            raise serializers.ValidationError(
                "Provide both lat and lng; radius_km also requires coordinates."
            )
        return attrs
