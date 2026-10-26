from django.contrib import admin

from .models import Achievement, JobSeekerProfile, Project, Skill, StatusHistory


class ProjectInline(admin.StackedInline):
    model = Project
    extra = 0


class AchievementInline(admin.TabularInline):
    model = Achievement
    extra = 0


class StatusHistoryInline(admin.TabularInline):
    """Read-only: history must never be edited or deleted by hand."""

    model = StatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(JobSeekerProfile)
class JobSeekerProfileAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "status", "score", "professional_role", "current_city")
    list_filter = ("status", "experience_type")
    search_fields = (
        "user__email", "first_name", "last_name", "professional_role", "skills__name",
    )
    filter_horizontal = ("skills",)
    readonly_fields = ("score", "score_breakdown", "score_updated_at", "created_at", "updated_at")
    inlines = [ProjectInline, AchievementInline, StatusHistoryInline]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    search_fields = ("name",)