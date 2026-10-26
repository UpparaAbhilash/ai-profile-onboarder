"""The profile status workflow. EVERY status change must go through change_status()."""
from django.db import transaction

from dashboard.models import AuditLog

from ..models import JobSeekerProfile, StatusHistory
from .completeness import missing_required_fields

Status = JobSeekerProfile.Status

CANDIDATE = "candidate"
REVIEWER = "reviewer"
REVIEW_PERMISSION = "profiles.review_profile"

# current status -> {allowed new status: who may make this change}
TRANSITIONS = {
    Status.CREATED: {
        Status.REVIEWED: REVIEWER,
        Status.OPEN_TO_WORK: CANDIDATE,
        Status.NOT_INTERESTED: CANDIDATE,
    },
    Status.REVIEWED: {
        Status.OPEN_TO_WORK: CANDIDATE,
        Status.NOT_INTERESTED: CANDIDATE,
    },
    Status.OPEN_TO_WORK: {Status.NOT_INTERESTED: CANDIDATE},
    Status.NOT_INTERESTED: {Status.OPEN_TO_WORK: CANDIDATE},
}


class StatusChangeError(Exception):
    """The requested change is not allowed. The message is safe to show to users."""


def label(value: str) -> str:
    return Status(value).label


def candidate_choices(profile: JobSeekerProfile) -> list[tuple[str, str]]:
    """Statuses the candidate may choose next, as (value, label) pairs."""
    return [
        (target, label(target))
        for target, role in TRANSITIONS.get(profile.status, {}).items()
        if role == CANDIDATE
    ]


def change_status(profile: JobSeekerProfile, new_status: str, actor, note: str = "") -> StatusHistory:
    """Validate and apply a status change, recording history and an audit entry."""
    if new_status not in Status.values:
        raise StatusChangeError("Unknown status.")

    with transaction.atomic():
        # Lock the row: a parallel request waits here and then sees the NEW status.
        locked = JobSeekerProfile.objects.select_for_update().get(pk=profile.pk)
        old_status = locked.status

        allowed = TRANSITIONS.get(old_status, {})
        if new_status not in allowed:
            raise StatusChangeError(
                f"The status cannot change from '{label(old_status)}' to '{label(new_status)}'."
            )

        role = allowed[new_status]
        if role == CANDIDATE and actor.pk != locked.user_id:
            raise StatusChangeError("Only the candidate can choose this status.")
        if role == REVIEWER and not actor.has_perm(REVIEW_PERMISSION):
            raise StatusChangeError("You do not have permission to review profiles.")

        if new_status == Status.OPEN_TO_WORK:
            missing = missing_required_fields(locked)
            if missing:
                raise StatusChangeError(
                    "Please complete your profile first. Missing: " + ", ".join(missing) + "."
                )

        locked.status = new_status
        locked.save(update_fields=["status", "updated_at"])
        entry = StatusHistory.objects.create(
            profile=locked,
            from_status=old_status,
            to_status=new_status,
            changed_by=actor,
            note=note[:255],
        )
        AuditLog.objects.create(
            actor=actor,
            action="profile.status_changed",
            target=locked,
            details={"from": old_status, "to": new_status, "role": role},
        )

    profile.status = new_status  # keep the caller's object up to date
    return entry