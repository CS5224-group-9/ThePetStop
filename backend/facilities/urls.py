from django.urls import path

from .views import location_search

urlpatterns = [
    path("locations/search/", location_search, name="location-search"),
]
