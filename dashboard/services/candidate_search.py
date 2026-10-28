"""Build the candidate search query from validated filter values."""
from django.db.models import F, Q

from profiles.models import JobSeekerProfile

SORT_ORDER = {
    "score": [F("score").desc(), F("updated_at").desc()],
    "newest": [F("created_at").desc()],
    "experience": [F("total_experience_months").desc(nulls_last=True), F("score").desc()],
    "name": [F("first_name").asc(), F("last_name").asc()],
}


def search_candidates(filters: dict):
    """Return profiles matching ALL given filters. Unknown or empty filters are ignored."""
    qs = JobSeekerProfile.objects.select_related("user").prefetch_related("skills")

    q = filters.get("q")
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(user__email__icontains=q)
            | Q(professional_role__icontains=q)
        )

    # One filter per skill = the candidate must have ALL of them.
    for skill in filters.get("skills") or []:
        qs = qs.filter(skills__name__iexact=skill)

    city = filters.get("city")
    if city:
        qs = qs.filter(Q(current_city__icontains=city) | Q(preferred_locations__icontains=city))

    if filters.get("status"):
        qs = qs.filter(status=filters["status"])
    if filters.get("experience_type"):
        qs = qs.filter(experience_type=filters["experience_type"])

    if filters.get("min_years") is not None:
        qs = qs.filter(total_experience_months__gte=filters["min_years"] * 12)
    if filters.get("max_years") is not None:
        # Freshers without a number count as 0 years.
        qs = qs.filter(
            Q(total_experience_months__lte=filters["max_years"] * 12)
            | Q(total_experience_months__isnull=True)
        )

    if filters.get("min_score") is not None:
        qs = qs.filter(score__gte=filters["min_score"])

    sort = filters.get("sort") or "score"
    return qs.distinct().order_by(*SORT_ORDER.get(sort, SORT_ORDER["score"]))