"""Create Resume records from validated uploads and extract their text."""
import logging
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction

from ..models import Resume
from .pdf_extraction import ExtractionError, extract_text
from .pdf_validation import ValidatedPDF

logger = logging.getLogger(__name__)

SCANNED_PDF_MESSAGE = (
    "This PDF looks like a scanned image and contains almost no selectable text. "
    "Please upload a PDF exported from Word, Google Docs or a similar editor."
)


def safe_original_filename(name: str) -> str:
    """Keep only the file name (no folder parts) and limit its length."""
    return Path(name).name[:255] or "resume.pdf"


def create_resume(validated: ValidatedPDF, original_filename: str, owner=None) -> Resume:
    """Store the PDF, create the database row and extract the text."""
    resume = Resume(
        owner=owner,
        original_filename=safe_original_filename(original_filename),
        file_size=validated.size,
        sha256=validated.sha256,
        page_count=validated.page_count,
        status=Resume.Status.PROCESSING,
    )

    # Write the file to disk under a random name (see resume_upload_path).
    # save=False: the database row is written in the next step.
    resume.file.save("upload.pdf", ContentFile(validated.data), save=False)
    try:
        with transaction.atomic():
            resume.save()
    except Exception:
        resume.file.delete(save=False)  # never leave an orphan file on disk
        raise

    try:
        result = extract_text(validated.data)
    except ExtractionError:
        logger.exception("Text extraction failed for resume id=%s", resume.pk)
        resume.status = Resume.Status.FAILED
        resume.error_message = "We could not read the text in this PDF."
    else:
        resume.extracted_text = result.text
        resume.page_count = result.page_count
        if result.needs_ocr:
            resume.status = Resume.Status.FAILED
            resume.error_message = SCANNED_PDF_MESSAGE
        else:
            resume.status = Resume.Status.EXTRACTED

    resume.save(
        update_fields=["extracted_text", "page_count", "status", "error_message", "updated_at"]
    )
    return resume
