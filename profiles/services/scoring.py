"""Profile score (0-100): how complete and detailed a profile is.

It does NOT judge the person or rank candidates by quality. Every point
comes from a visible rule, and every missing point comes with a tip.
"""
from dataclasses import dataclass, field

from django.utils import timezone

from ..models import JobSeekerProfile
from .completeness import (
    LOCATION_ITEM,
    MIN_SKILLS,
    REQUIRED_CHECK_COUNT,
    SKILLS_ITEM,
    missing_required_fields,
)

CATEGORIES = [
    ("completeness", "Profile completeness", 30),
    ("experience", "Experience", 20),
    ("skills", "Skills", 20),
    ("projects", "Projects", 15),
    ("achievements", "Certifications and awards", 5),
    ("preferences", "Job preferences", 10),
]

MAX_SKILLS_COUNTED = 10
POINTS_PER_SKILL = 2
MAX_PROJECTS_COUNTED = 3
MAX_POINTS_PER_PROJECT = 5
MAX_EXPERIENCE_MONTHS = 60       # 5 years gives the full 10 points
MIN_SUMMARY_CHARS = 100
MIN_PROJECT_DESCRIPTION_CHARS = 30
MAX_TIPS = 5


@dataclass(frozen=True)
class Tip:
    text: str
    points: int


@dataclass
class ScoreResult:
    total: int
    breakdown: dict           # key -> {"label", "points", "max"}
    tips: list[Tip] = field(default_factory=list)


def project_points(project) -> int:
    points = 1  # the project exists and has a title
    if len(project.description.strip()) >= MIN_PROJECT_DESCRIPTION_CHARS:
        points += 2
    if project.start_date:
        points += 1
    if project.role or project.activities.strip():
        points += 1
    return points


def missing_project_parts(project) -> list[str]:
    parts = []
    if len(project.description.strip()) < MIN_PROJECT_DESCRIPTION_CHARS:
        parts.append("a description")
    if not project.start_date:
        parts.append("dates")
    if not (project.role or project.activities.strip()):
        parts.append("your role or activities")
    return parts


def calculate_score(profile: JobSeekerProfile) -> ScoreResult:
    points: dict[str, int] = {}
    tips: list[Tip] = []

    # 1. Completeness (30): each required item is worth 30 / 9 points.
    missing = missing_required_fields(profile)
    done = REQUIRED_CHECK_COUNT - len(missing)
    if not profile.experience_type:
        done -= 1  # the "total experience" check can only pass once the type is known
    points["completeness"] = round(30 * done / REQUIRED_CHECK_COUNT)
    per_item = round(30 / REQUIRED_CHECK_COUNT)
    for item in missing:
        if item in (SKILLS_ITEM, LOCATION_ITEM):
            continue  # covered by the skills and preferences tips below
        gain = per_item + (5 if item.startswith("Experience type") else 0)
        tips.append(Tip(f"Add your {item.lower()}", gain))

    # 2. Experience (20)
    experience = 0
    if profile.experience_type:
        experience += 5
    if len(profile.experience_summary.strip()) >= MIN_SUMMARY_CHARS:
        experience += 5
    else:
        tips.append(Tip(f"Write an experience summary (at least {MIN_SUMMARY_CHARS} characters)", 5))
    months = min(profile.total_experience_months or 0, MAX_EXPERIENCE_MONTHS)
    experience += round(months / MAX_EXPERIENCE_MONTHS * 10)
    points["experience"] = experience

    # 3. Skills (20)
    skill_count = profile.skills.count()
    points["skills"] = min(skill_count, MAX_SKILLS_COUNTED) * POINTS_PER_SKILL
    if skill_count < MAX_SKILLS_COUNTED:
        more = MAX_SKILLS_COUNTED - skill_count
        gain = more * POINTS_PER_SKILL + (per_item if skill_count < MIN_SKILLS else 0)
        tips.append(Tip(f"Add up to {more} more skill(s): tools, languages and frameworks you have used", gain))

    # 4. Projects (15): the best 3 projects count.
    projects = sorted(profile.projects.all(), key=project_points, reverse=True)
    counted = projects[:MAX_PROJECTS_COUNTED]
    points["projects"] = sum(project_points(p) for p in counted)
    for project in counted:
        parts = missing_project_parts(project)
        if parts:
            tips.append(Tip(
                f"Improve the project '{project.title}': add {', '.join(parts)}",
                MAX_POINTS_PER_PROJECT - project_points(project),
            ))
    if len(projects) < MAX_PROJECTS_COUNTED:
        more = MAX_PROJECTS_COUNTED - len(projects)
        tips.append(Tip(
            f"Add {more} more project(s) with a description, dates and your role",
            more * MAX_POINTS_PER_PROJECT,
        ))

    # 5. Certifications and awards (5)
    achievement_count = profile.achievements.count()
    points["achievements"] = 0 if achievement_count == 0 else 3 if achievement_count == 1 else 5
    if achievement_count < 2:
        tips.append(Tip("Add a certification or award", 5 - points["achievements"]))

    # 6. Job preferences (10)
    preferences = 0
    if profile.preferred_roles:
        preferences += 5
    else:
        tips.append(Tip("Add at least one preferred role", 5))
    if profile.preferred_locations:
        preferences += 5
    else:
        tips.append(Tip("Add at least one preferred location", 5 + per_item))
    points["preferences"] = preferences

    breakdown = {
        key: {"label": label, "points": points[key], "max": maximum}
        for key, label, maximum in CATEGORIES
    }
    total = min(sum(points.values()), 100)
    tips.sort(key=lambda tip: tip.points, reverse=True)
    return ScoreResult(total=total, breakdown=breakdown, tips=tips[:MAX_TIPS])


def update_profile_score(profile: JobSeekerProfile) -> ScoreResult:
    """Recalculate and store the score."""
    result = calculate_score(profile)
    now = timezone.now()
    # .update() writes only these columns and does not touch updated_at:
    # recalculating a score is not an edit by the candidate.
    JobSeekerProfile.objects.filter(pk=profile.pk).update(
        score=result.total, score_breakdown=result.breakdown, score_updated_at=now
    )
    profile.score, profile.score_breakdown, profile.score_updated_at = result.total, result.breakdown, now
    return result