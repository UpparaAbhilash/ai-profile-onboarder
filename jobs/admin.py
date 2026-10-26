from django.contrib import admin

from .models import Application, Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "location", "employment_type", "is_active", "created_at")
    list_filter = ("is_active", "employment_type")
    search_fields = ("title", "company", "location")
    filter_horizontal = ("required_skills",)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("job", "candidate", "status", "applied_at")
    list_filter = ("status",)
    search_fields = ("job__title", "candidate__user__email")
    autocomplete_fields = ("job", "candidate")