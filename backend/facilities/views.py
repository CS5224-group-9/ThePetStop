from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from .onemap import client
from .serializers import LocationSearchQuerySerializer


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
