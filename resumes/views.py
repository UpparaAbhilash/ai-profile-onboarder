"""Resume upload, result page and protected download."""
from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from accounts.services.onboarding import onboard_from_resume

from .forms import ResumeUploadForm
from .models import Resume
from .permissions import can_access_resume, find_duplicate_upload, remember_upload
from .services.resume_intake import create_resume
from .services.resume_parsing import parse_and_store

PREVIEW_CHARS = 1500


def notify_about_account(request, resume: Resume) -> None:
    """Create an account for anonymous uploads. The message is the same for new and
    existing emails, so this page never reveals who already has an account."""
    outcome = onboard_from_resume(resume)
    if outcome == "no_email":
        messages.warning(
            request,
            "We could not find a valid email address in your resume, so no account was created. "
            "Please check the email in your resume and upload it again.",
        )
    elif outcome in ("created", "exists"):
        messages.info(
            request,
            "Check your inbox: if this email address is new to us, we sent you a link to set your "
            "password. Already have an account? Log in, and this resume will be linked to it.",
        )


@require_http_methods(["GET", "POST"])
def upload_resume(request):
    if request.method == "POST":
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            validated = form.validated_pdf

            duplicate = find_duplicate_upload(request, validated.sha256)
            if duplicate:
                # An earlier upload may not have been analysed yet (e.g. the AI was unavailable).
                if duplicate.status == Resume.Status.EXTRACTED:
                    parse_and_store(duplicate)
                messages.info(request, "You already uploaded this file. Showing your earlier upload.")
                return redirect("resumes:detail", pk=duplicate.pk)

            owner = request.user if request.user.is_authenticated else None
            resume = create_resume(validated, form.cleaned_data["file"].name, owner=owner)
            remember_upload(request, resume)

            # Runs inside the request for now; Phase 11 moves it to a background task.
            if resume.status == Resume.Status.EXTRACTED:
                resume = parse_and_store(resume)

            if resume.status == Resume.Status.PARSED:
                messages.success(request, "Your resume was analysed. Please check the extracted details.")
                if not request.user.is_authenticated:
                    notify_about_account(request, resume)
            elif resume.status == Resume.Status.FAILED:
                messages.warning(request, resume.error_message)
            else:
                messages.warning(
                    request,
                    "Your resume was uploaded and its text extracted, but the AI analysis did not complete.",
                )
            return redirect("resumes:detail", pk=resume.pk)
    else:
        form = ResumeUploadForm()

    return render(
        request,
        "resumes/upload.html",
        {"form": form, "max_mb": settings.RESUME_MAX_UPLOAD_MB},
    )


def get_accessible_resume(request, pk: int) -> Resume:
    """Return the resume, or 404 if it does not exist OR the user may not see it."""
    resume = get_object_or_404(Resume, pk=pk)
    if not can_access_resume(request, resume):
        raise Http404("Resume not found.")
    return resume


def build_parsed_context(resume: Resume) -> dict:
    """Prepare the AI result for the template."""
    parsed = resume.parsed_data or {}
    fields = parsed.get("fields")
    if not fields:
        return {"fields": None, "ai_warnings": [], "full_name": "", "experience_years": None}

    names = (fields.get("first_name"), fields.get("last_name"), fields.get("surname"))
    months = fields.get("total_experience_months")
    return {
        "fields": fields,
        "ai_warnings": parsed.get("warnings", []),
        "full_name": " ".join(name for name in names if name),
        "experience_years": round(months / 12, 1) if months is not None else None,
    }


@never_cache
@require_GET
def resume_detail(request, pk):
    resume = get_accessible_resume(request, pk)
    context = {
        "resume": resume,
        "preview": resume.extracted_text[:PREVIEW_CHARS],
        "preview_truncated": len(resume.extracted_text) > PREVIEW_CHARS,
    }
    context.update(build_parsed_context(resume))
    return render(request, "resumes/detail.html", context)


@never_cache
@require_GET
def download_resume(request, pk):
    resume = get_accessible_resume(request, pk)
    return FileResponse(
        resume.file.open("rb"),
        as_attachment=True,
        filename=resume.original_filename,
        content_type="application/pdf",
    )