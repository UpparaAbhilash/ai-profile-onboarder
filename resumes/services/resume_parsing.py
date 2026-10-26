"""Run AI parsing for a stored resume and save the result."""
import logging

from django.utils import timezone

from ..models import Resume
from .ai_parser import ResumeParsingError, parse_resume_text
from profiles.services.profile_import import import_profile_from_resume

logger = logging.getLogger(__name__)

PARSEABLE_STATUSES = {Resume.Status.EXTRACTED, Resume.Status.PARSED}


def parse_and_store(resume: Resume, client=None) -> Resume:
    """Parse the resume's extracted text with the AI and store the result.

    - Scanned/failed resumes are skipped (nothing is sent to the AI).
    - On AI errors the status is NOT changed, so the resume can be re-parsed later.
    - Logged-in uploads get their profile filled straight away.
    """
    if resume.status not in PARSEABLE_STATUSES or not resume.extracted_text:
        logger.info("Resume id=%s not sent to AI (status=%s).", resume.pk, resume.status)
        return resume

    try:
        result = parse_resume_text(resume.extracted_text, client=client)
    except ResumeParsingError as exc:
        # Our messages contain no personal data, so they are safe to log.
        logger.warning(
            "AI parsing failed for resume id=%s (retryable=%s): %s", resume.pk, exc.retryable, exc
        )
        resume.error_message = f"AI analysis failed: {exc}"
        resume.save(update_fields=["error_message", "updated_at"])
        return resume

    resume.parsed_data = {"fields": result.data, "warnings": result.warnings}
    resume.ai_model = result.model
    resume.status = Resume.Status.PARSED
    resume.error_message = ""
    resume.parsed_at = timezone.now()
    resume.save(
        update_fields=["parsed_data", "ai_model", "status", "error_message", "parsed_at", "updated_at"]
    )
    logger.info(
        "Resume id=%s parsed with %s (%d warnings).", resume.pk, result.model, len(result.warnings)
    )

    # Logged-in uploads get their profile filled straight away.
    # (Anonymous uploads are linked to an account in Phase 7.)
    if resume.owner_id:
        try:
            import_profile_from_resume(resume, resume.owner)
        except Exception:
            logger.exception("Profile import failed for resume id=%s.", resume.pk)
    return resume