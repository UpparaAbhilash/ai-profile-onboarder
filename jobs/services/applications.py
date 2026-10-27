"""Applying for jobs, withdrawing, and reviewer status changes.

All application rules live here; views and the admin only call these functions.
"""
from django.db import IntegrityError, transaction

from dashboard.models import AuditLog
from profiles.models import JobSeekerProfile
from profiles.services.completeness import missing_required_fields

from ..models import Application

AppStatus = Application.Status
REVIEW_PERMISSION = "jobs.change_application"

# Reviewer moves: current status -> allowed new statuses
REVIEW_TRANSITIONS = {
    AppStatus.SUBMITTED: {AppStatus.UNDER_REVIEW, AppStatus.REJECTED},
    AppStatus.UNDER_REVIEW: {AppStatus.SHORTLISTED, AppStatus.REJECTED},
    AppStatus.SHORTLISTED: {AppStatus.REJECTED},
}
# The candidate may withdraw only before being shortlisted.
WITHDRAWABLE = {AppStatus.SUBMITTED, AppStatus.UNDER_REVIEW}


class ApplicationError(Exception):
    """The action is not allowed. The message is safe to show to users."""


def skill_match(profile, job) -> dict:
    """Compare the job's required skills with the candidate's skills (case-insensitive)."""
    required = list(job.required_skills.all())
    if not required:
        return {"matched": [], "missing": [], "percent": None}
    have = {skill.name.casefold() for skill in profile.skills.all()} if profile else set()
    matched = [s.name for s in required if s.name.casefold() in have]
    missing = [s.name for s in required if s.name.casefold() not in have]
    return {"matched": matched, "missing": missing, "percent": round(100 * len(matched) / len(required))}


def apply_to_job(profile: JobSeekerProfile, job, cover_note: str = "") -> Application:
    if not job.is_active:
        raise ApplicationError("This job is no longer accepting applications.")
    if profile.status == JobSeekerProfile.Status.NOT_INTERESTED:
        raise ApplicationError(
            "Your availability is 'Not Interested'. Change it to 'Open to Work' on your profile to apply."
        )
    missing = missing_required_fields(profile)
    if missing:
        raise ApplicationError(
            "Please complete your profile before applying. Missing: " + ", ".join(missing) + "."
        )

    cover_note = cover_note.strip()
    with transaction.atomic():
        existing = (
            Application.objects.select_for_update().filter(job=job, candidate=profile).first()
        )
        if existing and existing.status != AppStatus.WITHDRAWN:
            raise ApplicationError("You have already applied for this job.")

        if existing:
            # Applying again after withdrawing re-uses the same row (the unique
            # constraint allows only one application per job and candidate).
            existing.status = AppStatus.SUBMITTED
            existing.cover_note = cover_note
            existing.save(update_fields=["status", "cover_note", "updated_at"])
            application, action = existing, "application.resubmitted"
        else:
            try:
                with transaction.atomic():  # savepoint: a failed insert leaves the outer transaction usable
                    application = Application.objects.create(
                        job=job, candidate=profile, cover_note=cover_note
                    )
            except IntegrityError:
                # Two requests at the same moment: the database constraint stopped the second one.
                raise ApplicationError("You have already applied for this job.") from None
            action = "application.submitted"

        AuditLog.objects.create(
            actor=profile.user, action=action, target=application, details={"job_id": job.pk}
        )
    return application


def withdraw_application(application: Application, actor) -> None:
    if application.candidate.user_id != actor.pk:
        raise ApplicationError("You can only withdraw your own applications.")

    with transaction.atomic():
        locked = Application.objects.select_for_update().get(pk=application.pk)
        if locked.status not in WITHDRAWABLE:
            raise ApplicationError(
                f"An application with status '{locked.get_status_display()}' can no longer be withdrawn."
            )
        old_status = locked.status
        locked.status = AppStatus.WITHDRAWN
        locked.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(
            actor=actor, action="application.withdrawn", target=locked, details={"from": old_status}
        )
    application.status = AppStatus.WITHDRAWN


def change_application_status(application: Application, new_status: str, actor) -> None:
    """Reviewer action: move an application forward or reject it."""
    if new_status not in AppStatus.values:
        raise ApplicationError("Unknown status.")

    with transaction.atomic():
        locked = Application.objects.select_for_update().get(pk=application.pk)
        old_status = locked.status
        if new_status not in REVIEW_TRANSITIONS.get(old_status, set()):
            raise ApplicationError(
                f"The status cannot change from '{AppStatus(old_status).label}' "
                f"to '{AppStatus(new_status).label}'."
            )
        if not actor.has_perm(REVIEW_PERMISSION):
            raise ApplicationError("You do not have permission to review applications.")

        locked.status = new_status
        locked.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(
            actor=actor,
            action="application.status_changed",
            target=locked,
            details={"from": old_status, "to": new_status},
        )
    application.status = new_status