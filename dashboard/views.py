"""Reviewer dashboard: overview, candidate search and candidate review."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from jobs.models import Application, Job
from jobs.services.applications import REVIEW_TRANSITIONS, ApplicationError, change_application_status
from profiles.models import JobSeekerProfile
from profiles.services.scoring import calculate_score
from profiles.services.status import StatusChangeError, change_status

from .forms import CandidateFilterForm
from .models import AuditLog
from .services.candidate_search import search_candidates

REVIEW_PERMISSION = "profiles.review_profile"
PAGE_SIZE = 20
# Order in which reviewer buttons are shown
APPLICATION_STEPS = [
    Application.Status.UNDER_REVIEW,
    Application.Status.SHORTLISTED,
    Application.Status.REJECTED,
]


def reviewer_required(view):
    """Anonymous -> login page. Logged in without the permission -> 403 Forbidden."""
    return login_required(permission_required(REVIEW_PERMISSION, raise_exception=True)(view))


def client_ip(request):
    return request.META.get("REMOTE_ADDR") or None


@reviewer_required
@require_GET
def home(request):
    profile_counts = {
        row["status"]: row["n"]
        for row in JobSeekerProfile.objects.order_by().values("status").annotate(n=Count("id"))
    }
    application_counts = {
        row["status"]: row["n"]
        for row in Application.objects.order_by().values("status").annotate(n=Count("id"))
    }
    return render(request, "dashboard/home.html", {
        "profile_cards": [
            (value, label, profile_counts.get(value, 0))
            for value, label in JobSeekerProfile.Status.choices
        ],
        "application_cards": [
            (value, label, application_counts.get(value, 0))
            for value, label in Application.Status.choices
        ],
        "open_jobs": Job.objects.filter(is_active=True).count(),
        "recent_activity": AuditLog.objects.select_related("actor").exclude(action="profile.viewed")[:10],
    })


@reviewer_required
@require_GET
def candidate_list(request):
    form = CandidateFilterForm(request.GET or None)
    filters = form.cleaned_data if form.is_bound and form.is_valid() else {}
    page_obj = Paginator(search_candidates(filters), PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "dashboard/candidate_list.html", {"form": form, "page_obj": page_obj})


@reviewer_required
@require_GET
def candidate_detail(request, pk):
    profile = get_object_or_404(
        JobSeekerProfile.objects.select_related("user", "source_resume")
        .prefetch_related("skills", "projects", "achievements"),
        pk=pk,
    )
    # Who looked at whose personal data, and when (GDPR accountability).
    AuditLog.objects.create(
        actor=request.user, action="profile.viewed", target=profile, ip_address=client_ip(request)
    )

    applications = list(profile.applications.select_related("job"))
    for application in applications:
        allowed = REVIEW_TRANSITIONS.get(application.status, set())
        application.next_steps = [(step, step.label) for step in APPLICATION_STEPS if step in allowed]

    profile_type = ContentType.objects.get_for_model(JobSeekerProfile)
    application_type = ContentType.objects.get_for_model(Application)
    activity = (
        AuditLog.objects.filter(
            Q(content_type=profile_type, object_id=str(profile.pk))
            | Q(content_type=application_type, object_id__in=[str(a.pk) for a in applications])
        )
        .exclude(action="profile.viewed")
        .select_related("actor")[:30]
    )

    return render(request, "dashboard/candidate_detail.html", {
        "profile": profile,
        "score": calculate_score(profile),
        "applications": applications,
        "resumes": profile.user.resumes.all(),
        "status_history": profile.status_history.select_related("changed_by"),
        "activity": activity,
        "can_review": profile.status == JobSeekerProfile.Status.CREATED,
    })


@reviewer_required
@require_POST
def review_candidate(request, pk):
    profile = get_object_or_404(JobSeekerProfile, pk=pk)
    note = request.POST.get("note", "").strip()[:255] or "Reviewed in the dashboard."
    try:
        change_status(profile, JobSeekerProfile.Status.REVIEWED, request.user, note=note)
    except StatusChangeError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "The profile was marked as reviewed.")
    return redirect("dashboard:candidate_detail", pk=profile.pk)


@reviewer_required
@require_POST
def application_status(request, pk):
    application = get_object_or_404(Application.objects.select_related("job"), pk=pk)
    new_status = request.POST.get("status", "")
    try:
        change_application_status(application, new_status, request.user)
    except ApplicationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Application for '{application.job.title}' is now '{Application.Status(new_status).label}'.",
        )
    return redirect("dashboard:candidate_detail", pk=application.candidate_id)