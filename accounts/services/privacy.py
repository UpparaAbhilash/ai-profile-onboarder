"""GDPR: right to erasure and data retention.

Important: Django deletes database rows, but NEVER the files behind a FileField.
Every deletion here therefore removes the PDF files explicitly, after the
database change has been committed.
"""
import logging
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX
from django.db import transaction
from django.utils import timezone

from dashboard.models import AuditLog
from jobs.models import Application
from resumes.models import Resume

logger = logging.getLogger(__name__)
User = get_user_model()

ORPHAN_FILE_MIN_AGE_SECONDS = 60 * 60  # never touch a file that is being uploaded right now


def delete_files_after_commit(resumes) -> None:
    """Remove the PDFs once the database deletion is final (not if it is rolled back)."""
    files = [(resume.file.storage, resume.file.name) for resume in resumes if resume.file]

    def remove_files():
        for storage, name in files:
            storage.delete(name)  # does nothing if the file is already gone

    transaction.on_commit(remove_files)


def delete_resumes(queryset) -> int:
    resumes = list(queryset)
    with transaction.atomic():
        delete_files_after_commit(resumes)
        Resume.objects.filter(pk__in=[resume.pk for resume in resumes]).delete()
    return len(resumes)


def delete_account(user, *, reason: str) -> dict:
    """Delete a user and ALL their personal data. Returns counts only, never personal data."""
    # Resumes uploaded with this email that were never linked to the account.
    unlinked = list(
        Resume.objects.filter(owner__isnull=True, parsed_data__fields__email=user.email.lower())
    )
    resumes = list(user.resumes.all()) + unlinked
    counts = {
        "resumes": len(resumes),
        "applications": Application.objects.filter(candidate__user=user).count(),
    }
    with transaction.atomic():
        delete_files_after_commit(resumes)
        Resume.objects.filter(pk__in=[resume.pk for resume in unlinked]).delete()
        # CASCADE removes: owned resumes, profile, projects, achievements,
        # status history and applications.
        user.delete()
        AuditLog.objects.create(action="account.deleted", details={"reason": reason, **counts})
    logger.info("Account deleted (reason=%s): %s", reason, counts)
    return counts


def find_orphan_files(now_timestamp=None):
    """PDF files on disk that no Resume row points to (e.g. left over from crashes)."""
    now_timestamp = now_timestamp or time.time()
    media_root = Path(settings.MEDIA_ROOT)
    known = set(Resume.objects.values_list("file", flat=True))
    orphans = []
    for path in (media_root / "resumes").rglob("*.pdf"):
        if path.relative_to(media_root).as_posix() in known:
            continue
        if now_timestamp - path.stat().st_mtime < ORPHAN_FILE_MIN_AGE_SECONDS:
            continue
        orphans.append(path)
    return orphans


def purge_old_data(*, dry_run: bool = False) -> dict:
    """Delete everything that is past its retention period (see the privacy page)."""
    now = timezone.now()
    unclaimed_cutoff = now - timedelta(days=settings.UNCLAIMED_DATA_RETENTION_DAYS)
    audit_cutoff = now - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)

    # Accounts created from a resume whose owner never set a password and never logged in.
    # Accounts with a usable password (e.g. reviewers created by an admin) are never touched.
    inactive_accounts = User.objects.filter(
        password__startswith=UNUSABLE_PASSWORD_PREFIX,
        last_login__isnull=True,
        date_joined__lt=unclaimed_cutoff,
        is_staff=False,
        is_superuser=False,
    )
    unclaimed_resumes = Resume.objects.filter(owner__isnull=True, created_at__lt=unclaimed_cutoff)
    old_audit_entries = AuditLog.objects.filter(created_at__lt=audit_cutoff)

    if dry_run:
        return {
            "inactive accounts": inactive_accounts.count(),
            "unclaimed resumes": unclaimed_resumes.count(),
            "audit log entries": old_audit_entries.count(),
            "orphan files": len(find_orphan_files()),
        }

    accounts = 0
    for user in inactive_accounts:
        delete_account(user, reason="retention")
        accounts += 1
    counts = {
        "inactive accounts": accounts,
        "unclaimed resumes": delete_resumes(unclaimed_resumes),  # those not removed above
        "audit log entries": old_audit_entries.delete()[0],
        "orphan files": 0,
    }
    for path in find_orphan_files():
        path.unlink(missing_ok=True)
        counts["orphan files"] += 1

    AuditLog.objects.create(action="data.purged", details=counts)
    return counts