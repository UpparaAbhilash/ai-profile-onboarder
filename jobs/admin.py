from django.contrib import admin
from django.db.models import Count

from .models import Application, Job
from .services.applications import ApplicationError, change_application_status


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "location", "employment_type", "is_active",
                    "application_count", "created_at")
    list_filter = ("is_active", "employment_type")
    search_fields = ("title", "company", "location")
    filter_horizontal = ("required_skills",)
    readonly_fields = ("created_by", "created_at", "updated_at")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(num_applications=Count("applications"))

    @admin.display(description="Applications", ordering="num_applications")
    def application_count(self, obj):
        return obj.num_applications

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("job", "candidate", "status", "applied_at")
    list_filter = ("status", "job")
    search_fields = ("job__title", "job__company", "candidate__user__email",
                     "candidate__first_name", "candidate__last_name")
    list_select_related = ("job", "candidate", "candidate__user")
    # Everything is read-only: status changes go through the actions (rules + audit log).
    readonly_fields = ("job", "candidate", "status", "cover_note", "applied_at", "updated_at")
    actions = ["mark_under_review", "mark_shortlisted", "mark_rejected"]

    def has_add_permission(self, request):
        return False  # applications are created only by candidates, through the rules

    def _change_selected(self, request, queryset, new_status):
        done = skipped = 0
        for application in queryset:
            try:
                change_application_status(application, new_status, request.user)
            except ApplicationError:
                skipped += 1
            else:
                done += 1
        label = Application.Status(new_status).label
        self.message_user(request, f"{done} application(s) changed to '{label}'.")
        if skipped:
            self.message_user(
                request,
                f"{skipped} application(s) skipped: that change is not allowed from their current status.",
                level="warning",
            )

    @admin.action(description="Mark as under review", permissions=["change"])
    def mark_under_review(self, request, queryset):
        self._change_selected(request, queryset, Application.Status.UNDER_REVIEW)

    @admin.action(description="Mark as shortlisted", permissions=["change"])
    def mark_shortlisted(self, request, queryset):
        self._change_selected(request, queryset, Application.Status.SHORTLISTED)

    @admin.action(description="Mark as rejected", permissions=["change"])
    def mark_rejected(self, request, queryset):
        self._change_selected(request, queryset, Application.Status.REJECTED)