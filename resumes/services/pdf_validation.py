"""Validate uploaded resume files before they are stored or processed.

Never trust the file name or the browser's content type: both are
controlled by the uploader. We check size, the real file signature,
and whether PyMuPDF can actually open the document.
"""
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from django.conf import settings

logger = logging.getLogger(__name__)

PDF_SIGNATURE = b"%PDF-"


class ResumeValidationError(Exception):
    """The uploaded file is not an acceptable resume. The message is safe to show users."""


@dataclass(frozen=True)
class ValidatedPDF:
    data: bytes
    sha256: str
    size: int
    page_count: int


def validate_resume_file(uploaded_file) -> ValidatedPDF:
    """Run all checks on an uploaded file and return its validated contents.

    Raises ResumeValidationError with a user-friendly message on failure.
    """
    max_mb = settings.RESUME_MAX_UPLOAD_MB
    max_bytes = max_mb * 1024 * 1024

    # 1. Extension: a cheap first filter, never trusted on its own.
    if Path(uploaded_file.name).suffix.lower() != ".pdf":
        raise ResumeValidationError("Only PDF files are accepted.")

    # 2. Size: checked BEFORE reading the whole file into memory.
    if uploaded_file.size == 0:
        raise ResumeValidationError("The file is empty.")
    if uploaded_file.size > max_bytes:
        raise ResumeValidationError(f"The file is too large. The maximum size is {max_mb} MB.")

    uploaded_file.seek(0)
    data = uploaded_file.read()
    uploaded_file.seek(0)

    # 3. Real content: every PDF contains the %PDF- signature near the start.
    if PDF_SIGNATURE not in data[:1024]:
        raise ResumeValidationError("This file is not a real PDF, even though its name ends in .pdf.")

    # 4. Structure: can the PDF library actually open it?
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:  # PyMuPDF raises several different error types for broken files
        logger.info("Rejected damaged PDF upload: %s", uploaded_file.name)
        raise ResumeValidationError("The PDF is damaged and cannot be read.") from None

    with doc:
        # 5. Password protection: we cannot read encrypted content.
        if doc.needs_pass:
            raise ResumeValidationError(
                "The PDF is password-protected. Please upload an unprotected copy."
            )
        page_count = doc.page_count

    # 6. Page count.
    if page_count == 0:
        raise ResumeValidationError("The PDF has no pages.")
    if page_count > settings.RESUME_MAX_PAGES:
        raise ResumeValidationError(
            f"The PDF has {page_count} pages. A resume may have at most "
            f"{settings.RESUME_MAX_PAGES} pages."
        )

    return ValidatedPDF(
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        page_count=page_count,
    )