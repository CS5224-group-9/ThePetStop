from django.db.models import Case, F, FloatField, Value, When
from django.db.models.functions import ASin, Cos, Greatest, Least, Radians, Sin, Sqrt
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from .models import Facility
from .onemap import client
from .serializers import (
    FacilityQuerySerializer,
    FacilitySerializer,
    LocationSearchQuerySerializer,
)


class FacilityListView(ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = FacilitySerializer
    queryset = Facility.objects.filter(active=True).order_by("name", "id")

    def get_queryset(self):
        query = FacilityQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        facilities = super().get_queryset()
        if "type" in filters:
            facilities = facilities.filter(facility_type=filters["type"])
        if "animal" in filters:
            facilities = facilities.filter(
                facility_type=Facility.Type.PET_SHOP,
                approved_animals__contains=[filters["animal"]],
            )
        if "lat" in filters:
            lat, lng = filters["lat"], filters["lng"]
            if "radius_km" in filters:
                delta = filters["radius_km"] / 6371 * 180 / 3.141592653589793
                facilities = facilities.filter(
                    latitude__gte=lat - delta, latitude__lte=lat + delta
                )
            a = (
                Sin(Radians((F("latitude") - lat) / 2)) ** 2
                + Cos(Radians(Value(lat)))
                * Cos(Radians(F("latitude")))
                * Sin(Radians((F("longitude") - lng) / 2)) ** 2
            )
            distance = 2 * 6371 * ASin(Sqrt(Least(Value(1.0), Greatest(Value(0.0), a))))
            facilities = facilities.annotate(
                distance_km=Case(
                    When(
                        latitude__isnull=False, longitude__isnull=False, then=distance
                    ),
                    output_field=FloatField(),
                )
            )
            if "radius_km" in filters:
                facilities = facilities.filter(distance_km__lte=filters["radius_km"])
            facilities = facilities.order_by(
                F("distance_km").asc(nulls_last=True), "name", "id"
            )
        return facilities

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class LocationSearchThrottle(SimpleRateThrottle):
    scope = "location_search"
    rate = "30/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([LocationSearchThrottle])
def location_search(request):
    query = LocationSearchQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    response = Response({"results": client.search(query.validated_data["q"])})
    response["Cache-Control"] = "no-store"
    return response
