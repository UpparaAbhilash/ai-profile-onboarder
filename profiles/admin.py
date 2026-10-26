from django.contrib import admin

from .models import Achievement, JobSeekerProfile, Project, Skill, StatusHistory
from .services.status import REVIEW_PERMISSION, StatusChangeError, change_status


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
    # status is read-only: changes must go through the workflow (history + audit log).
    readonly_fields = (
        "status", "score", "score_breakdown", "score_updated_at", "created_at", "updated_at",
    )
    inlines = [ProjectInline, AchievementInline, StatusHistoryInline]
    actions = ["mark_reviewed"]

    @admin.action(description="Mark selected profiles as reviewed", permissions=["review"])
    def mark_reviewed(self, request, queryset):
        done = failed = 0
        for profile in queryset:
            try:
                change_status(profile, JobSeekerProfile.Status.REVIEWED, request.user,
                              note="Reviewed in the admin.")
            except StatusChangeError:
                failed += 1
            else:
                done += 1
        self.message_user(request, f"{done} profile(s) marked as reviewed.")
        if failed:
            self.message_user(
                request,
                f"{failed} profile(s) skipped: only profiles with status 'Created' can be reviewed.",
                level="warning",
            )

    def has_review_permission(self, request):
        return request.user.has_perm(REVIEW_PERMISSION)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    search_fields = ("name",)