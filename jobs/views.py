"""Job listings, job details, applying and the candidate's application history."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from profiles.models import JobSeekerProfile
from profiles.services.completeness import missing_required_fields

from .forms import ApplicationForm
from .models import Application, Job
from .services.applications import (
    WITHDRAWABLE,
    ApplicationError,
    apply_to_job,
    skill_match,
    withdraw_application,
)

PAGE_SIZE = 10


def get_profile(user):
    if not user.is_authenticated:
        return None
    return JobSeekerProfile.objects.filter(user=user).prefetch_related("skills").first()


@require_GET
def job_list(request):
    q = request.GET.get("q", "").strip()[:100]
    selected_type = request.GET.get("type", "")

    jobs = Job.objects.filter(is_active=True).prefetch_related("required_skills")
    if q:
        jobs = jobs.filter(
            Q(title__icontains=q)
            | Q(company__icontains=q)
            | Q(location__icontains=q)
            | Q(required_skills__name__icontains=q)
        ).distinct()
    if selected_type in Job.EmploymentType.values:
        jobs = jobs.filter(employment_type=selected_type)

    page_obj = Paginator(jobs, PAGE_SIZE).get_page(request.GET.get("page"))

    applied_job_ids = set()
    if request.user.is_authenticated:
        applied_job_ids = set(
            Application.objects.filter(candidate__user=request.user)
            .exclude(status=Application.Status.WITHDRAWN)
            .values_list("job_id", flat=True)
        )

    return render(request, "jobs/job_list.html", {
        "page_obj": page_obj,
        "q": q,
        "selected_type": selected_type,
        "employment_types": Job.EmploymentType.choices,
        "applied_job_ids": applied_job_ids,
    })


def apply_state(user, profile, application, missing_fields) -> str:
    """Decide which box the job page shows on the right."""
    if not user.is_authenticated:
        return "login"
    if profile is None:
        return "no_profile"
    if application and application.status != Application.Status.WITHDRAWN:
        return "applied"
    if profile.status == JobSeekerProfile.Status.NOT_INTERESTED:
        return "not_interested"
    if missing_fields:
        return "incomplete"
    return "can_apply"


@require_GET
def job_detail(request, pk):
    job = get_object_or_404(Job.objects.prefetch_related("required_skills"), pk=pk, is_active=True)
    profile = get_profile(request.user)
    application = Application.objects.filter(job=job, candidate=profile).first() if profile else None
    missing_fields = missing_required_fields(profile) if profile else []

    return render(request, "jobs/job_detail.html", {
        "job": job,
        "profile": profile,
        "application": application,
        "match": skill_match(profile, job),
        "missing_fields": missing_fields,
        "state": apply_state(request.user, profile, application, missing_fields),
        "form": ApplicationForm(),
        "min_years": round(job.min_experience_months / 12, 1) if job.min_experience_months else None,
    })


@login_required
@require_POST
def apply(request, pk):
    job = get_object_or_404(Job, pk=pk, is_active=True)
    profile = JobSeekerProfile.objects.filter(user=request.user).first()
    if profile is None:
        messages.info(request, "Upload your resume first. We will create your profile from it.")
        return redirect("resumes:upload")

    form = ApplicationForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Your cover note is too long (maximum 2000 characters).")
        return redirect("jobs:detail", pk=job.pk)

    try:
        apply_to_job(profile, job, form.cleaned_data["cover_note"])
    except ApplicationError as exc:
        messages.error(request, str(exc))
        return redirect("jobs:detail", pk=job.pk)

    messages.success(request, f"You applied for '{job.title}' at {job.company}.")
    return redirect("jobs:my_applications")


@login_required
@require_GET
def my_applications(request):
    applications = Application.objects.filter(candidate__user=request.user).select_related("job")
    return render(request, "jobs/my_applications.html", {
        "applications": applications,
        "withdrawable": list(WITHDRAWABLE),
    })


@login_required
@require_POST
def withdraw(request, pk):
    # candidate__user=request.user: someone else's application gives 404 (no IDOR).
    application = get_object_or_404(
        Application.objects.select_related("job", "candidate"), pk=pk, candidate__user=request.user
    )
    try:
        withdraw_application(application, request.user)
    except ApplicationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Your application for '{application.job.title}' was withdrawn.")
    return redirect("jobs:my_applications")