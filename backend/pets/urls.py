from django.urls import path, include
from . import views
urlpatterns = [
    path('pets/',views.PetListCreateView.as_view(),name="pet-list"),
    path('pets/<int:pk>/',views.PetDetailView.as_view(),name="pet-detail")
]
path("api/v1/", include("pets.urls")),