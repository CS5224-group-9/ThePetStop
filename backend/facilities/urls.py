from django.urls import path

from .views import FacilityListView, location_search

urlpatterns = [
    path("facilities/", FacilityListView.as_view(), name="facility-list"),
    path("locations/search/", location_search, name="location-search"),
]
