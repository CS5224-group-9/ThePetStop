from django.contrib import admin
from .models import pet
@admin.register(pet)
class petAdmin(admin.ModelAdmin):
    list_display = ["name","species","owner", "created_at"]
    list_filter = ["species","sex"]
    search_fields = ["name","breeds","owner__username"]


