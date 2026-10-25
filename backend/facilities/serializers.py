from rest_framework import serializers


class LocationSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=120, trim_whitespace=True)

    def validate_q(self, value):
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise serializers.ValidationError("Enter an address or postal code.")
        return value
