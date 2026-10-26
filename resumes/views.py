"""Resume upload, result page and protected download."""
from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .forms import ResumeUploadForm
from .models import Resume
from .permissions import can_access_resume, find_duplicate_upload, remember_upload
from .services.resume_intake import create_resume

PREVIEW_CHARS = 1500


@require_http_methods(["GET", "POST"])
def upload_resume(request):
    if request.method == "POST":
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            validated = form.validated_pdf

            duplicate = find_duplicate_upload(request, validated.sha256)
            if duplicate:
                messages.info(request, "You already uploaded this file. Showing your earlier upload.")
                return redirect("resumes:detail", pk=duplicate.pk)

            owner = request.user if request.user.is_authenticated else None
            resume = create_resume(validated, form.cleaned_data["file"].name, owner=owner)
            remember_upload(request, resume)

            if resume.status == Resume.Status.FAILED:
                messages.warning(request, resume.error_message)
            else:
                messages.success(request, "Your resume was uploaded and its text was extracted.")
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


@never_cache
@require_GET
def resume_detail(request, pk):
    resume = get_accessible_resume(request, pk)
    preview = resume.extracted_text[:PREVIEW_CHARS]
    return render(
        request,
        "resumes/detail.html",
        {
            "resume": resume,
            "preview": preview,
            "preview_truncated": len(resume.extracted_text) > PREVIEW_CHARS,
        },
    )


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