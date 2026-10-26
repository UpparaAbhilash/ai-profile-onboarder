"""Create a FAKE sample resume PDF for manual testing (no real personal data).

Usage:
    python manage.py make_sample_resume --email priya.test@example.com
"""
import pymupdf
from django.core.management.base import BaseCommand

SAMPLE = """Priya Sharma
{email} | +49 151 23456789 | Berlin, Germany

Python Developer with 2 years of experience in Django and MySQL.

Experience
Python Developer, Example GmbH, 2024-01 to present

Skills: Python, Django, MySQL, REST APIs, Git

Projects
Library Management System (2023-03 to 2023-08)
Built a Django web app for book loans with MySQL and Bootstrap.

Certifications
Python for Everybody, Coursera, 2023
"""


class Command(BaseCommand):
    help = "Create a fake sample resume PDF for testing account onboarding."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="priya.test@example.com")
        parser.add_argument("--output", default="sample_resume.pdf")

    def handle(self, *args, email, output, **options):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), SAMPLE.format(email=email), fontsize=11)
        doc.save(output)
        self.stdout.write(self.style.SUCCESS(f"Created {output} with email {email}"))