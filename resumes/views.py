"""Resume upload, result page and protected download."""
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .forms import ResumeUploadForm
from .models import Resume
from .permissions import can_access_resume, find_duplicate_upload, remember_upload
from .services.resume_intake import create_resume
from .tasks import queue_parsing

PREVIEW_CHARS = 1500
REFRESH_SECONDS = 4                       # how often the page reloads while the AI works
ANALYSIS_TIMEOUT = timedelta(minutes=15)  # stop reloading after this (e.g. worker not running)


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
                    duplicate.error_message = ""
                    duplicate.save(update_fields=["error_message", "updated_at"])
                    queue_parsing(duplicate.pk)
                messages.info(request, "You already uploaded this file. Showing your earlier upload.")
                return redirect("resumes:detail", pk=duplicate.pk)

            owner = request.user if request.user.is_authenticated else None
            resume = create_resume(validated, form.cleaned_data["file"].name, owner=owner)
            remember_upload(request, resume)

            # The slow AI step runs in the Celery worker; this request answers at once.
            if resume.status == Resume.Status.EXTRACTED:
                queue_parsing(resume.pk)
                messages.success(request, "Your resume was uploaded. Our AI is analysing it now.")
            else:
                messages.warning(request, resume.error_message)
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


def build_analysis_context(request, resume: Resume) -> dict:
    """Is the AI still working? Should we tell an anonymous uploader about the email?"""
    waiting = resume.status == Resume.Status.EXTRACTED and not resume.error_message
    too_long = waiting and timezone.now() - resume.updated_at > ANALYSIS_TIMEOUT
    return {
        "analysing": waiting and not too_long,
        "analysis_slow": too_long,
        "refresh_seconds": REFRESH_SECONDS,
        "account_notice": (
            not request.user.is_authenticated
            and resume.status == Resume.Status.PARSED
            and not resume.owner_id
        ),
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
    context.update(build_analysis_context(request, resume))
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