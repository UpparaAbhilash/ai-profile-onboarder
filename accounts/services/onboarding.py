"""Create accounts from parsed resumes and link resumes after email verification.

Security rules:
- New accounts start with an UNUSABLE password; no password is ever emailed.
- The set-password link is one-time and expires (PASSWORD_RESET_TIMEOUT).
- A resume is linked to an account only after the email owner proves control
  (set-password link or normal login), never just because a resume names an email.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from profiles.services.profile_import import import_profile_from_resume
from resumes.models import Resume

logger = logging.getLogger(__name__)


def build_set_password_url(user) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    return settings.SITE_URL.rstrip("/") + path


def send_onboarding_email(user) -> None:
    context = {
        "user": user,
        "set_password_url": build_set_password_url(user),
        "valid_hours": settings.PASSWORD_RESET_TIMEOUT // 3600,
    }
    subject = render_to_string("accounts/email/onboarding_subject.txt", context).strip()
    body = render_to_string("accounts/email/onboarding_email.txt", context)
    send_mail(subject, body, None, [user.email])  # None -> DEFAULT_FROM_EMAIL


def onboard_from_resume(resume) -> str:
    """Create an account for the email found in an anonymous, parsed resume.

    Returns one of: "created", "exists", "no_email", "skipped".
    """
    if resume.owner_id or resume.status != Resume.Status.PARSED:
        return "skipped"

    fields = (resume.parsed_data or {}).get("fields") or {}
    email = fields.get("email")
    if not email:
        return "no_email"

    User = get_user_model()
    if User.objects.filter(email__iexact=email).exists():
        return "exists"

    try:
        with transaction.atomic():
            user = User.objects.create_user(  # password=None -> unusable password
                email=email,
                first_name=(fields.get("first_name") or "")[:150],
                last_name=(fields.get("last_name") or "")[:150],
            )
    except IntegrityError:  # someone created the same email at the same moment
        return "exists"

    try:
        send_onboarding_email(user)
    except Exception:
        # The account stays; the user can still use "Forgot password?" later.
        logger.exception("Onboarding email failed for user id=%s.", user.pk)
    logger.info("Account user id=%s created from resume id=%s.", user.pk, resume.pk)
    return "created"


def link_pending_resumes(user) -> int:
    """Attach unowned, parsed resumes whose email matches this (verified) user."""
    if not user.email:
        return 0
    pending = list(
        Resume.objects.filter(
            owner__isnull=True,
            status=Resume.Status.PARSED,
            parsed_data__fields__email=user.email.lower(),
        ).order_by("-created_at")  # newest resume first
    )
    for resume in pending:
        resume.owner = user
        resume.save(update_fields=["owner", "updated_at"])
        try:
            import_profile_from_resume(resume, user)
        except Exception:
            logger.exception("Profile import failed for resume id=%s.", resume.pk)
    if pending:
        logger.info("Linked %d resume(s) to user id=%s.", len(pending), user.pk)
    return len(pending)