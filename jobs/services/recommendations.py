"""Job recommendations: open jobs that fit the candidate's skills.

The candidate always decides: this only suggests jobs, it never applies.
"""
from ..models import Application, Job
from .applications import skill_match

MIN_MATCH_PERCENT = 50  # show only jobs where the candidate has at least half of the skills
MAX_RECOMMENDATIONS = 5


def recommend_jobs(profile, limit=MAX_RECOMMENDATIONS, min_percent=MIN_MATCH_PERCENT):
    """Return up to `limit` (job, match) pairs, best match first.

    Skipped: closed jobs, jobs without required skills, jobs the candidate
    already applied for (a withdrawn application may be suggested again).
    """
    if profile is None:
        return []

    applied_job_ids = (
        Application.objects.filter(candidate=profile)
        .exclude(status=Application.Status.WITHDRAWN)
        .values_list("job_id", flat=True)
    )
    # Let MySQL do the first filter: only open jobs that share at least one skill.
    candidates = (
        Job.objects.filter(is_active=True, required_skills__in=profile.skills.all())
        .exclude(pk__in=applied_job_ids)
        .distinct()
        .prefetch_related("required_skills")
    )

    results = []
    for job in candidates:
        match = skill_match(profile, job)
        if match["percent"] is not None and match["percent"] >= min_percent:
            results.append((job, match))

    # Best match first; for the same match, the newest job first.
    results.sort(key=lambda pair: (pair[1]["percent"], pair[0].created_at), reverse=True)
    return results[:limit]
