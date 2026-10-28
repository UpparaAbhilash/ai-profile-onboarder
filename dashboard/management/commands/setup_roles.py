"""Create the Reviewer group with exactly the permissions it needs.

Usage:
    python manage.py setup_roles
    python manage.py setup_roles --add reviewer@example.com
Safe to run more than once.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

REVIEWER_GROUP = "Reviewer"
REVIEWER_PERMISSIONS = [
    "profiles.review_profile",
    "profiles.view_jobseekerprofile",
    "resumes.view_resume",
    "jobs.view_job",
    "jobs.view_application",
    "jobs.change_application",
    "dashboard.view_auditlog",
]


class Command(BaseCommand):
    help = "Create or update the Reviewer group, and optionally add users to it."

    def add_arguments(self, parser):
        parser.add_argument("--add", action="append", default=[], metavar="EMAIL",
                            help="Add this user to the Reviewer group (can be repeated).")

    def handle(self, *args, add, **options):
        permissions = []
        for name in REVIEWER_PERMISSIONS:
            app_label, codename = name.split(".")
            try:
                permissions.append(
                    Permission.objects.get(content_type__app_label=app_label, codename=codename)
                )
            except Permission.DoesNotExist:
                raise CommandError(f"Permission {name} not found. Did you run 'migrate'?")

        group, created = Group.objects.get_or_create(name=REVIEWER_GROUP)
        group.permissions.set(permissions)
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} group '{REVIEWER_GROUP}' with {len(permissions)} permissions."))

        User = get_user_model()
        for email in add:
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                raise CommandError(f"No user with email {email}.")
            user.groups.add(group)
            self.stdout.write(self.style.SUCCESS(f"Added {user.email} to '{REVIEWER_GROUP}'."))