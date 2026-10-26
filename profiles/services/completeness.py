"""Which fields a profile needs before the candidate can be 'Open to Work'.

Scoring reuses this, so the rules exist in exactly one place.
"""
from ..models import JobSeekerProfile

MIN_SKILLS = 3

REQUIRED_TEXT_FIELDS = [
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("phone", "Phone"),
    ("current_city", "Current city"),
    ("professional_role", "Professional role"),
    ("experience_type", "Experience type (fresher or experienced)"),
]

EXPERIENCE_ITEM = "Total experience"
SKILLS_ITEM = f"At least {MIN_SKILLS} skills"
LOCATION_ITEM = "At least one preferred location"

# 6 text fields + total experience + skills + preferred location
REQUIRED_CHECK_COUNT = len(REQUIRED_TEXT_FIELDS) + 3


def missing_required_fields(profile: JobSeekerProfile) -> list[str]:
    """Return human-readable names of everything still missing (empty list = complete)."""
    missing = [label for field, label in REQUIRED_TEXT_FIELDS if not getattr(profile, field)]

    if (
        profile.experience_type == JobSeekerProfile.ExperienceType.EXPERIENCED
        and profile.total_experience_months is None
    ):
        missing.append(EXPERIENCE_ITEM)

    if profile.skills.count() < MIN_SKILLS:
        missing.append(SKILLS_ITEM)

    if not profile.preferred_locations:
        missing.append(LOCATION_ITEM)

    return missing