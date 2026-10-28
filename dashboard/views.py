"""Reviewer dashboard: overview, candidates, jobs pipeline, audit log and CSV export."""
import csv
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from jobs.models import Application, Job
from jobs.services.applications import (
    REVIEW_TRANSITIONS,
    ApplicationError,
    change_application_status,
    skill_match,
)
from profiles.models import JobSeekerProfile
from profiles.services.scoring import calculate_score
from profiles.services.status import StatusChangeError, change_status

from .forms import AuditFilterForm, CandidateFilterForm
from .models import AuditLog
from .services.candidate_search import search_candidates

REVIEW_PERMISSION = "profiles.review_profile"
AUDIT_PERMISSION = "dashboard.view_auditlog"
PAGE_SIZE = 20
AUDIT_PAGE_SIZE = 50
MAX_EXPORT_ROWS = 5000
# Order in which reviewer buttons are shown
APPLICATION_STEPS = [
    Application.Status.UNDER_REVIEW,
    Application.Status.SHORTLISTED,
    Application.Status.REJECTED,
]
# Cells starting with these characters are treated as formulas by spreadsheet programs.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
CSV_HEADER = [
    "Name", "Professional role", "Current city", "Experience (years)",
    "Skills", "Score", "Status", "Profile link",
]


def reviewer_required(view):
    """Anonymous -> login page. Logged in without the permission -> 403 Forbidden."""
    return login_required(permission_required(REVIEW_PERMISSION, raise_exception=True)(view))


def client_ip(request):
    return request.META.get("REMOTE_ADDR") or None


def next_steps_for(application):
    """Status buttons a reviewer may use for this application."""
    allowed = REVIEW_TRANSITIONS.get(application.status, set())
    return [(step, step.label) for step in APPLICATION_STEPS if step in allowed]


def safe_cell(value) -> str:
    """Neutralise spreadsheet formulas (CSV injection)."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


# ---------------------------------------------------------------------------
# Overview and candidates (Part A)
# ---------------------------------------------------------------------------
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
        application.next_steps = next_steps_for(application)

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

    # Go back to the page the button was on, but ONLY if it is on our own site.
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("dashboard:candidate_detail", pk=application.candidate_id)


# ---------------------------------------------------------------------------
# CSV export (Part B)
# ---------------------------------------------------------------------------
@reviewer_required
@require_GET
def export_candidates(request):
    form = CandidateFilterForm(request.GET or None)
    if form.is_bound and not form.is_valid():
        messages.error(request, "Please correct the filters before exporting.")
        return redirect("dashboard:candidate_list")
    filters = form.cleaned_data if form.is_bound else {}

    candidates = list(search_candidates(filters)[:MAX_EXPORT_ROWS])

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="candidates-{timezone.localdate():%Y-%m-%d}.csv"'
    )
    response.write("\ufeff")  # byte order mark: Excel then reads umlauts and Indian scripts correctly
    writer = csv.writer(response)
    writer.writerow(CSV_HEADER)
    for profile in candidates:
        writer.writerow([safe_cell(value) for value in (
            profile.full_name or profile.user.email.split("@")[0],
            profile.professional_role,
            profile.current_city,
            profile.total_experience_years,
            ", ".join(skill.name for skill in profile.skills.all()),
            profile.score,
            profile.get_status_display(),
            request.build_absolute_uri(reverse("dashboard:candidate_detail", args=[profile.pk])),
        )])

    AuditLog.objects.create(
        actor=request.user,
        action="candidates.exported",
        details={
            "rows": len(candidates),
            "filters": {k: v for k, v in filters.items() if v not in (None, "", [])},
        },
        ip_address=client_ip(request),
    )
    return response


# ---------------------------------------------------------------------------
# Jobs pipeline (Part B)
# ---------------------------------------------------------------------------
@reviewer_required
@require_GET
def job_pipeline(request):
    S = Application.Status
    jobs = Job.objects.annotate(
        total=Count("applications", filter=~Q(applications__status=S.WITHDRAWN)),
        new=Count("applications", filter=Q(applications__status=S.SUBMITTED)),
        in_review=Count("applications", filter=Q(applications__status=S.UNDER_REVIEW)),
        shortlisted=Count("applications", filter=Q(applications__status=S.SHORTLISTED)),
    ).order_by("-is_active", "-created_at")
    return render(request, "dashboard/job_pipeline.html", {"jobs": jobs})


@reviewer_required
@require_GET
def job_applicants(request, pk):
    job = get_object_or_404(Job.objects.prefetch_related("required_skills"), pk=pk)
    status = request.GET.get("status", "")

    applications = job.applications.select_related("candidate__user").prefetch_related("candidate__skills")
    if status in Application.Status.values:
        applications = applications.filter(status=status)
    else:
        status = ""
        applications = applications.exclude(status=Application.Status.WITHDRAWN)

    rows = list(applications)
    for application in rows:
        application.match = skill_match(application.candidate, job)
        application.next_steps = next_steps_for(application)
    # Best skill match first; equal matches by profile score.
    rows.sort(key=lambda a: (a.match["percent"] or 0, a.candidate.score), reverse=True)

    return render(request, "dashboard/job_applicants.html", {
        "job": job,
        "applications": rows,
        "status": status,
        "status_choices": Application.Status.choices,
    })


# ---------------------------------------------------------------------------
# Audit log browser (Part B)
# ---------------------------------------------------------------------------
@reviewer_required
@permission_required(AUDIT_PERMISSION, raise_exception=True)
@require_GET
def audit_log(request):
    form = AuditFilterForm(request.GET or None)
    entries = AuditLog.objects.select_related("actor", "content_type")

    if form.is_bound and form.is_valid():
        data = form.cleaned_data
        if data["action"]:
            entries = entries.filter(action=data["action"])
        if data["actor"]:
            entries = entries.filter(actor__email__icontains=data["actor"])
        tz = timezone.get_current_timezone()
        if data["date_from"]:
            entries = entries.filter(created_at__gte=datetime.combine(data["date_from"], time.min, tzinfo=tz))
        if data["date_to"]:
            next_day = data["date_to"] + timedelta(days=1)
            entries = entries.filter(created_at__lt=datetime.combine(next_day, time.min, tzinfo=tz))

    page_obj = Paginator(entries, AUDIT_PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "dashboard/audit_log.html", {"form": form, "page_obj": page_obj})