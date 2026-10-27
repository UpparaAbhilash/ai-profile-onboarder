"""Create sample jobs (fake companies) for development and demos.

Usage: python manage.py seed_jobs
"""
from django.core.management.base import BaseCommand

from jobs.models import Job
from profiles.services.profile_import import get_or_create_skill

SAMPLE_JOBS = [
    {
        "title": "Junior Python Developer", "company": "Example GmbH", "location": "Berlin",
        "employment_type": "full_time", "min_experience_months": 0,
        "skills": ["Python", "Django", "MySQL", "Git"],
        "description": "Sample job for testing.\n\nYou will build and maintain Django web applications "
                       "together with a small team. Good for graduates who know Python basics.",
    },
    {
        "title": "Backend Developer (Django)", "company": "Demo Tech AG", "location": "Munich",
        "employment_type": "full_time", "min_experience_months": 24,
        "skills": ["Python", "Django", "REST APIs", "Docker"],
        "description": "Sample job for testing.\n\nDesign REST APIs, write tests and deploy services with Docker.",
    },
    {
        "title": "Werkstudent GenAI Engineering", "company": "Sample AI Labs", "location": "Berlin",
        "employment_type": "part_time", "min_experience_months": 0,
        "skills": ["Python", "OpenAI API", "Pydantic", "Git"],
        "description": "Sample job for testing.\n\nWork 20 hours per week on LLM features: prompt design, "
                       "structured outputs and evaluation.",
    },
    {
        "title": "Data Analyst Intern", "company": "Acme Analytics", "location": "Hamburg",
        "employment_type": "internship", "min_experience_months": 0,
        "skills": ["Python", "SQL", "Excel"],
        "description": "Sample job for testing.\n\nClean data, build reports and present results to the team.",
    },
    {
        "title": "Full Stack Developer", "company": "Placeholder Software", "location": "Remote",
        "employment_type": "contract", "min_experience_months": 36,
        "skills": ["Python", "Django", "JavaScript", "Bootstrap"],
        "description": "Sample job for testing.\n\nBuild features end to end, from database to user interface.",
    },
    {
        "title": "Python Developer", "company": "Example Technologies", "location": "Hyderabad",
        "employment_type": "full_time", "min_experience_months": 12,
        "skills": ["Python", "Django", "MySQL", "REST APIs"],
        "description": "Sample job for testing.\n\nDevelop internal tools and APIs for a growing product team.",
    },
]


class Command(BaseCommand):
    help = "Create sample jobs for development. Safe to run more than once."

    def handle(self, *args, **options):
        created_count = 0
        for data in SAMPLE_JOBS:
            data = dict(data)
            skills = data.pop("skills")
            job, created = Job.objects.get_or_create(
                title=data.pop("title"), company=data.pop("company"), defaults=data
            )
            job.required_skills.set([get_or_create_skill(name) for name in skills])
            created_count += created
        existing = len(SAMPLE_JOBS) - created_count
        self.stdout.write(self.style.SUCCESS(
            f"Created {created_count} new job(s); {existing} already existed."
        ))