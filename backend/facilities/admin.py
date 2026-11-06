from django.contrib import admin

from facilities.models import (
    Facility,
    FacilitySourceState,
    FacilitySyncEvent,
    FacilitySyncRun,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FacilitySyncRun)
class RunAdmin(ReadOnlyAdmin):
    list_display = (
        "run_id",
        "source",
        "status",
        "stage",
        "completed_batch_count",
        "expected_batch_count",
        "retry_count",
        "last_activity_at",
        "error_code",
    )
    list_filter = ("source", "status", "stage")
    search_fields = ("run_id", "error_code")


@admin.register(FacilitySyncEvent)
class EventAdmin(ReadOnlyAdmin):
    list_display = ("event_id", "run", "stage", "kind", "occurred_at")
    list_filter = ("stage", "kind")


@admin.register(Facility)
class FacilityAdmin(ReadOnlyAdmin):
    list_display = ("name", "facility_type", "postal_code", "active", "last_checked_at")
    list_filter = ("facility_type", "active", "geocode_status")
    search_fields = ("name", "postal_code", "licence_no")


admin.site.register(FacilitySourceState, ReadOnlyAdmin)
