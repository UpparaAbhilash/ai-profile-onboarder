"""Candidate-facing profile pages."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from resumes.models import Resume

from .forms import AchievementFormSet, ProfileForm, ProjectFormSet
from .models import Achievement, JobSeekerProfile
from .services.completeness import missing_required_fields
from .services.profile_import import import_profile_from_resume
from .services.scoring import calculate_score, update_profile_score
from .services.status import StatusChangeError, candidate_choices, change_status, label


@login_required
@require_GET
def my_profile(request):
    profile = (
        JobSeekerProfile.objects.filter(user=request.user)
        .select_related("source_resume")
        .prefetch_related("skills", "projects", "achievements")
        .first()
    )
    context = {"profile": profile}
    if profile:
        achievements = list(profile.achievements.all())
        context.update(
            certifications=[a for a in achievements if a.kind == Achievement.Kind.CERTIFICATION],
            awards=[a for a in achievements if a.kind == Achievement.Kind.AWARD],
            status_choices=candidate_choices(profile),
            missing_fields=missing_required_fields(profile),
            status_history=profile.status_history.select_related("changed_by")[:10],
            score=calculate_score(profile),
        )
    return render(request, "profiles/detail.html", context)


@login_required
@require_POST
def change_my_status(request):
    profile = get_object_or_404(JobSeekerProfile, user=request.user)
    new_status = request.POST.get("status", "")
    try:
        change_status(profile, new_status, request.user, note="Changed by the candidate.")
    except StatusChangeError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Your status is now '{label(new_status)}'.")
    return redirect("profiles:me")


@login_required
@require_http_methods(["GET", "POST"])
def edit_profile(request):
    # Always the logged-in user's own profile: there is no ID in the URL to tamper with.
    profile = JobSeekerProfile.objects.filter(user=request.user).first()
    if profile is None:
        messages.info(request, "Upload your resume first. We will create your profile from it.")
        return redirect("resumes:upload")

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        projects = ProjectFormSet(request.POST, instance=profile, prefix="projects")
        achievements = AchievementFormSet(request.POST, instance=profile, prefix="achievements")

        # A list (not "and") so ALL three are validated and all errors are shown at once.
        if all([form.is_valid(), projects.is_valid(), achievements.is_valid()]):
            with transaction.atomic():  # everything is saved, or nothing
                profile = form.save()
                projects.save()
                achievements.save()
                update_profile_score(profile)
            messages.success(request, "Your profile was saved.")
            return redirect("profiles:me")
        messages.error(request, "Please correct the errors below.")
    else:
        form = ProfileForm(instance=profile)
        projects = ProjectFormSet(instance=profile, prefix="projects")
        achievements = AchievementFormSet(instance=profile, prefix="achievements")

    return render(
        request,
        "profiles/edit.html",
        {"form": form, "projects": projects, "achievements": achievements},
    )


@login_required
@require_POST
def import_from_resume(request, resume_pk):
    # owner=request.user: other people's resumes give 404, never someone else's data.
    resume = get_object_or_404(Resume, pk=resume_pk, owner=request.user)
    if resume.status != Resume.Status.PARSED:
        messages.error(request, "This resume has not been analysed yet.")
        return redirect("resumes:detail", pk=resume.pk)

    _, created = import_profile_from_resume(resume, request.user)
    if created:
        messages.success(request, "Your profile was created from your resume. Please review it.")
    else:
        messages.success(request, "Empty fields in your profile were filled from this resume.")
    return redirect("profiles:me")