"""Create or update a candidate profile from a parsed resume.

Golden rule: values the candidate already has are NEVER overwritten.
Only empty profile fields are filled, so re-importing a resume cannot
destroy corrections the candidate made by hand.
"""
import logging
from datetime import date

from django.db import transaction

from ..models import Achievement, JobSeekerProfile, Project, Skill, StatusHistory

logger = logging.getLogger(__name__)

TEXT_FIELDS = (
    "first_name",
    "last_name",
    "surname",
    "phone",
    "current_company",
    "professional_role",
    "current_city",
    "experience_summary",
    "experience_type",
    "aadhaar_last4",
)


def _limit(model, field_name: str, value: str) -> str:
    """Cut a string to the column's max_length (TextFields have none)."""
    max_length = model._meta.get_field(field_name).max_length
    return value[:max_length] if max_length else value


def _month_to_date(value):
    """'2023-02' -> date(2023, 2, 1). Anything else -> None."""
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except (AttributeError, ValueError):
        return None


def get_or_create_skill(name: str) -> Skill:
    name = " ".join(name.split())[:100]
    return Skill.objects.filter(name__iexact=name).first() or Skill.objects.create(name=name)


@transaction.atomic
def import_profile_from_resume(resume, user):
    """Fill the user's profile from resume.parsed_data. Returns (profile, created)."""
    fields = (resume.parsed_data or {}).get("fields")
    if not fields:
        raise ValueError(f"Resume {resume.pk} has no parsed data.")

    profile, created = JobSeekerProfile.objects.get_or_create(user=user)

    # 1. Simple text fields: only fill what is empty.
    for name in TEXT_FIELDS:
        value = fields.get(name)
        if value and not getattr(profile, name):
            setattr(profile, name, _limit(JobSeekerProfile, name, value))

    if profile.date_of_birth is None and fields.get("date_of_birth"):
        try:
            profile.date_of_birth = date.fromisoformat(fields["date_of_birth"])
        except ValueError:
            pass

    if profile.total_experience_months is None and fields.get("total_experience_months") is not None:
        profile.total_experience_months = fields["total_experience_months"]

    for name in ("preferred_locations", "preferred_roles"):
        if not getattr(profile, name) and fields.get(name):
            setattr(profile, name, fields[name])

    profile.source_resume = resume
    profile.save()

    # 2. Skills: add missing ones, re-using existing Skill rows.
    for skill_name in fields.get("skills", []):
        profile.skills.add(get_or_create_skill(skill_name))

    # 3. Projects and achievements: only if the profile has none yet (no duplicates).
    if not profile.projects.exists():
        for order, item in enumerate(fields.get("projects", [])):
            start = _month_to_date(item.get("start_month"))
            end = None if item.get("is_ongoing") else _month_to_date(item.get("end_month"))
            if start and end and end < start:
                end = None
            Project.objects.create(
                profile=profile,
                title=_limit(Project, "title", item["title"]),
                description=item.get("description") or "",
                role=_limit(Project, "role", item.get("role") or ""),
                activities="\n".join(item.get("activities") or []),
                start_date=start,
                end_date=end,
                order=order,
            )

    if not profile.achievements.exists():
        for kind, key in (
            (Achievement.Kind.CERTIFICATION, "certifications"),
            (Achievement.Kind.AWARD, "awards"),
        ):
            for item in fields.get(key, []):
                Achievement.objects.create(
                    profile=profile,
                    kind=kind,
                    title=_limit(Achievement, "title", item["title"]),
                    issuer=_limit(Achievement, "issuer", item.get("issuer") or ""),
                    year=item.get("year"),
                )

    # 4. Record the creation in the status history (audit trail).
    if created:
        StatusHistory.objects.create(
            profile=profile,
            from_status="",
            to_status=profile.status,
            changed_by=user,
            note="Profile created from resume.",
        )

    logger.info(
        "Profile id=%s %s from resume id=%s.",
        profile.pk, "created" if created else "updated", resume.pk,
    )
    return profile, created