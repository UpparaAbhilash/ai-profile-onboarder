"""Candidate-facing profile pages."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from resumes.models import Resume

from .models import Achievement, JobSeekerProfile
from .services.profile_import import import_profile_from_resume


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
        )
    return render(request, "profiles/detail.html", context)


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