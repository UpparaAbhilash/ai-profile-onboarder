"""Job listings, job details, applying and the candidate's application history."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from profiles.models import JobSeekerProfile
from profiles.services.completeness import missing_required_fields

from .forms import ApplicationForm, AutoApplyForm
from .models import Application, Job
from .services.applications import (
    WITHDRAWABLE,
    ApplicationError,
    apply_to_job,
    skill_match,
    withdraw_application,
)
from .services.auto_apply import AutoApplyError, get_rule, save_rule
from .services.cover_note import CoverNoteError, generate_cover_note, take_draft_slot
from .services.recommendations import MIN_MATCH_PERCENT, recommend_jobs

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


@login_required
@require_GET
def recommended(request):
    """Jobs that fit the candidate's skills. Suggestions only: the candidate still clicks Apply."""
    profile = get_profile(request.user)
    if profile is None:
        messages.info(request, "Upload your resume first. We will create your profile from it.")
        return redirect("resumes:upload")

    return render(request, "jobs/recommended.html", {
        "profile": profile,
        "recommendations": recommend_jobs(profile),
        "min_percent": MIN_MATCH_PERCENT,
        "not_interested": profile.status == JobSeekerProfile.Status.NOT_INTERESTED,
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


def get_open_job(pk):
    return get_object_or_404(Job.objects.prefetch_related("required_skills"), pk=pk, is_active=True)


def job_detail_context(request, job) -> dict:
    profile = get_profile(request.user)
    application = Application.objects.filter(job=job, candidate=profile).first() if profile else None
    missing_fields = missing_required_fields(profile) if profile else []
    return {
        "job": job,
        "profile": profile,
        "application": application,
        "match": skill_match(profile, job),
        "missing_fields": missing_fields,
        "state": apply_state(request.user, profile, application, missing_fields),
        "form": ApplicationForm(),
        "min_years": round(job.min_experience_months / 12, 1) if job.min_experience_months else None,
    }


def draft_session_key(job) -> str:
    return f"cover_note_draft_{job.pk}"


@require_GET
def job_detail(request, pk):
    job = get_open_job(pk)
    context = job_detail_context(request, job)

    # An AI draft from draft_cover_note (shown once, then removed from the session).
    draft = request.session.pop(draft_session_key(job), None)
    if draft and context["state"] == "can_apply":
        context["form"] = ApplicationForm(initial={"cover_note": draft})
        context["ai_draft"] = True

    return render(request, "jobs/job_detail.html", context)


@login_required
@require_POST
def draft_cover_note(request, pk):
    """Ask the AI for a cover note DRAFT. It never applies: the candidate edits and decides."""
    job = get_open_job(pk)
    context = job_detail_context(request, job)
    if context["state"] != "can_apply":
        messages.error(request, "You can only draft a cover note for a job you can apply for.")
        return redirect("jobs:detail", pk=job.pk)

    if not take_draft_slot(request.user):
        messages.error(
            request,
            f"You reached today's limit of {settings.COVER_NOTE_DAILY_LIMIT} AI drafts. "
            "Please write your note yourself or try again tomorrow.",
        )
        return redirect("jobs:detail", pk=job.pk)

    try:
        draft = generate_cover_note(context["profile"], job)
    except CoverNoteError as exc:
        messages.error(request, str(exc))
        return redirect("jobs:detail", pk=job.pk)

    # Post/Redirect/Get: reloading the page does not call the AI (and cost money) again.
    request.session[draft_session_key(job)] = draft
    return redirect("jobs:detail", pk=job.pk)


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
@login_required
@require_http_methods(["GET", "POST"])
def auto_apply_settings(request):
    """The candidate's auto-apply rules and consent. Nothing is applied here."""
    profile = get_profile(request.user)
    if profile is None:
        messages.info(request, "Upload your resume first. We will create your profile from it.")
        return redirect("resumes:upload")

    rule = get_rule(profile)
    if request.method == "POST":
        form = AutoApplyForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                save_rule(
                    profile,
                    request.user,
                    enabled=data["enabled"],
                    min_match_percent=data["min_match_percent"],
                    locations=data["locations"],
                    employment_types=data["employment_types"],
                    max_per_week=data["max_per_week"],
                )
            except AutoApplyError as exc:
                form.add_error(None, str(exc))
            else:
                if data["enabled"]:
                    messages.success(
                        request,
                        f"Auto-apply is on. We will apply for you to matching jobs, "
                        f"at most {data['max_per_week']} per week.",
                    )
                else:
                    messages.success(request, "Auto-apply is off. We will not apply for you.")
                return redirect("jobs:auto_apply")  # Post/Redirect/Get
    else:
        form = AutoApplyForm.from_rule(rule)

    return render(request, "jobs/auto_apply.html", {"form": form, "rule": rule})