"""Background tasks for resumes. The Celery worker runs these, not the web request.

Rules:
- Tasks receive only the resume ID, never resume text or personal data,
  so nothing personal is stored in Redis.
- Tasks are safe to run twice (idempotent): a resume that is already parsed
  is never sent to the AI again.
"""
import logging

from celery import shared_task
from django.db import transaction
from kombu.exceptions import OperationalError

from accounts.services.onboarding import onboard_from_resume

from .models import Resume
from .services.ai_parser import ResumeParsingError
from .services.resume_parsing import parse_and_store

logger = logging.getLogger(__name__)

# Wait longer after each temporary AI error: 30 s, then 60 s, then 120 s.
RETRY_DELAYS = (30, 60, 120)
QUEUE_ERROR_MESSAGE = "The AI analysis could not be started. Please try again later."


# ignore_result=True: the outcome lives in MySQL (status, parsed_data), so no Redis result
# backend is needed. This also means a Redis outage cannot crash the upload request.
@shared_task(
    bind=True, name="resumes.parse_resume", max_retries=len(RETRY_DELAYS), ignore_result=True
)
def parse_resume_task(self, resume_id: int) -> str:
    """Parse one resume with the AI, then create the account for anonymous uploads.

    Returns a short status word for the worker log (never personal data).
    """
    resume = Resume.objects.filter(pk=resume_id).first()
    if resume is None:
        logger.warning("Resume id=%s no longer exists; nothing to parse.", resume_id)
        return "missing"
    if resume.status != Resume.Status.EXTRACTED:
        # Already parsed, failed (e.g. scanned PDF) or not ready: nothing to do.
        return resume.status

    can_retry = self.request.retries < self.max_retries
    try:
        # On the last attempt, errors are saved on the resume instead of raised.
        resume = parse_and_store(resume, raise_retryable=can_retry)
    except ResumeParsingError as exc:
        delay = RETRY_DELAYS[self.request.retries]
        logger.info(
            "Temporary AI error for resume id=%s; retry %d in %ds.",
            resume_id, self.request.retries + 1, delay,
        )
        raise self.retry(exc=exc, countdown=delay)

    if resume.status != Resume.Status.PARSED:
        return "ai_failed"
    if resume.owner_id:
        return "parsed"  # logged-in upload: parse_and_store already filled the profile
    return f"parsed:{onboard_from_resume(resume)}"  # e.g. "parsed:created"


def queue_parsing(resume_id: int) -> None:
    """Send the parse task to the worker once the resume is safely saved in MySQL."""

    def send():
        try:
            parse_resume_task.delay(resume_id)
        except OperationalError:
            # Redis is down: the upload still works, the page shows a clear message,
            # and "python manage.py reparse_resume --pending" can finish the job later.
            logger.exception("Could not queue AI parsing for resume id=%s.", resume_id)
            Resume.objects.filter(pk=resume_id).update(error_message=QUEUE_ERROR_MESSAGE)

    transaction.on_commit(send)