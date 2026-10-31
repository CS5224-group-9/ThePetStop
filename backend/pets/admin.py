"""Staff-only. These pages show private pet and medical data; registered
deliberately for local debugging and the demo.

Admin deletes do not remove stored files (acceptable for a staff tool).
"""

from django.contrib import admin

from .models import HealthRecord, Pet, PetDocument, Reminder


@admin.register(Pet)
class PetAdmin(admin.ModelAdmin):
    list_display = ("name", "species", "owner", "created_at")
    list_filter = ("species",)
    search_fields = ("name", "owner__email", "owner__username")
    raw_id_fields = ("owner",)
    readonly_fields = (
        "photo_key",
        "photo_content_type",
        "pending_photo_key",
        "pending_photo_content_type",
        "pending_photo_size_bytes",
        "pending_photo_requested_at",
        "created_at",
        "updated_at",
    )


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ("name", "record_type", "pet", "date", "next_due")
    list_filter = ("record_type",)
    search_fields = ("name", "pet__name")
    raw_id_fields = ("pet",)


@admin.register(PetDocument)
class PetDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "pet",
        "content_type",
        "size_bytes",
        "status",
        "uploaded_at",
    )
    list_filter = ("status", "content_type")
    raw_id_fields = ("pet", "health_record")
    readonly_fields = (
        "file_key",
        "content_type",
        "size_bytes",
        "status",
        "uploaded_at",
        "created_at",
    )

    def has_add_permission(self, request):
        # Documents come only from the upload flow; the file fields are read-only
        return False


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("title", "pet", "due_at", "done")
    list_filter = ("done",)
    search_fields = ("title", "pet__name")
    raw_id_fields = ("pet", "health_record")
