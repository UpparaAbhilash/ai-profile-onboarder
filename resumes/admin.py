from django.contrib import admin

from .models import Resume


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "owner", "status", "page_count", "created_at")
    list_filter = ("status",)
    search_fields = ("original_filename", "owner__email")
    readonly_fields = ("sha256", "file_size", "page_count", "created_at", "updated_at", "parsed_at")