from django.urls import path

from . import views

# <str:...> rather than <uuid:...>: a malformed id reaches the view and becomes
# the enveloped 404 not_found, like any other id the user does not own.
urlpatterns = [
    path("pets/", views.PetListCreateView.as_view(), name="pet-list"),
    path("pets/<str:pk>/", views.PetDetailView.as_view(), name="pet-detail"),
    path(
        "pets/<str:pk>/photo-upload/",
        views.PetPhotoUploadView.as_view(),
        name="pet-photo-upload",
    ),
    path(
        "pets/<str:pk>/photo-upload/complete/",
        views.PetPhotoCompleteView.as_view(),
        name="pet-photo-complete",
    ),
    path("pets/<str:pk>/photo/", views.PetPhotoView.as_view(), name="pet-photo"),
    path(
        "pets/<str:pet_pk>/records/",
        views.HealthRecordListCreateView.as_view(),
        name="record-list",
    ),
    path(
        "pets/<str:pet_pk>/records/<str:pk>/",
        views.HealthRecordDetailView.as_view(),
        name="record-detail",
    ),
    path(
        "pets/<str:pet_pk>/documents/",
        views.DocumentListCreateView.as_view(),
        name="document-list",
    ),
    path(
        "pets/<str:pet_pk>/documents/<str:pk>/",
        views.DocumentDetailView.as_view(),
        name="document-detail",
    ),
    path(
        "pets/<str:pet_pk>/documents/<str:pk>/complete/",
        views.DocumentCompleteView.as_view(),
        name="document-complete",
    ),
    path("reminders/", views.ReminderListCreateView.as_view(), name="reminder-list"),
    path(
        "reminders/<str:pk>/",
        views.ReminderDetailView.as_view(),
        name="reminder-detail",
    ),
]
