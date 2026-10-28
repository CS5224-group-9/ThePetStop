from rest_framework import serializers

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
