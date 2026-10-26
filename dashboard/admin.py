from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Audit entries are read-only for everyone, including superusers."""

    list_display = ("created_at", "actor", "action", "content_type", "object_id")
    list_filter = ("action",)
    search_fields = ("action", "actor__email", "object_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False