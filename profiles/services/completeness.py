"""Which fields a profile needs before the candidate can be 'Open to Work'.

Part B (scoring) reuses this, so the rules exist in exactly one place.
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


def missing_required_fields(profile: JobSeekerProfile) -> list[str]:
    """Return human-readable names of everything still missing (empty list = complete)."""
    missing = [label for field, label in REQUIRED_TEXT_FIELDS if not getattr(profile, field)]

    if (
        profile.experience_type == JobSeekerProfile.ExperienceType.EXPERIENCED
        and profile.total_experience_months is None
    ):
        missing.append("Total experience")

    if profile.skills.count() < MIN_SKILLS:
        missing.append(f"At least {MIN_SKILLS} skills")

    if not profile.preferred_locations:
        missing.append("At least one preferred location")

    return missing