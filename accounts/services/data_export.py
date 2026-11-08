"""GDPR right of access (Art. 15) and portability (Art. 20):
everything we store about one user, as machine-readable JSON."""
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from jobs.models import Application
from profiles.models import JobSeekerProfile

PROFILE_FIELDS = [
    "first_name", "last_name", "surname", "phone", "date_of_birth", "aadhaar_last4",
    "experience_type", "total_experience_months", "current_company", "professional_role",
    "experience_summary", "current_city", "preferred_locations", "preferred_roles",
    "status", "score", "score_breakdown", "created_at", "updated_at",
]
PROJECT_FIELDS = ["title", "description", "role", "activities", "start_date", "end_date"]
ACHIEVEMENT_FIELDS = ["kind", "title", "issuer", "year"]
HISTORY_FIELDS = ["from_status", "to_status", "note", "created_at"]
RESUME_FIELDS = [
    "original_filename", "status", "page_count", "created_at", "parsed_at",
    "extracted_text", "parsed_data", "error_message",
]
NOT_INCLUDED = [
    "Uploaded PDF files: download them from each resume page.",
    "Your password: it is stored only as a one-way hash and cannot be exported.",
    "Reviewer activity logs: they contain other people's data (reviewers' accounts, IP addresses).",
]


def pick(obj, fields) -> dict:
    return {field: getattr(obj, field) for field in fields}


def build_export(user) -> dict:
    data = {
        "export_created_at": timezone.now(),
        "account": pick(user, ["email", "first_name", "last_name", "date_joined", "last_login"]),
        "profile": None,
        "resumes": [pick(resume, RESUME_FIELDS) for resume in user.resumes.all()],
        "applications": [],
        "not_included": NOT_INCLUDED,
    }
    profile = (
        JobSeekerProfile.objects.filter(user=user)
        .prefetch_related("skills", "projects", "achievements", "status_history")
        .first()
    )
    if profile:
        data["profile"] = {
            **pick(profile, PROFILE_FIELDS),
            "skills": sorted(skill.name for skill in profile.skills.all()),
            "projects": [pick(project, PROJECT_FIELDS) for project in profile.projects.all()],
            "achievements": [pick(item, ACHIEVEMENT_FIELDS) for item in profile.achievements.all()],
            "status_history": [pick(entry, HISTORY_FIELDS) for entry in profile.status_history.all()],
        }
        data["applications"] = [
            {
                "job_title": application.job.title,
                "company": application.job.company,
                "status": application.status,
                "cover_note": application.cover_note,
                "applied_at": application.applied_at,
                "updated_at": application.updated_at,
            }
            for application in Application.objects.filter(candidate=profile).select_related("job")
        ]
    return data


def export_as_json(user) -> str:
    # DjangoJSONEncoder turns dates and datetimes into ISO 8601 text.
    return json.dumps(build_export(user), cls=DjangoJSONEncoder, indent=2, ensure_ascii=False)