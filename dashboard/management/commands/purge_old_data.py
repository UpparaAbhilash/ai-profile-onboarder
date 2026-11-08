"""Delete personal data that is past its retention period.

    python manage.py purge_old_data --dry-run   # only show what would be deleted
    python manage.py purge_old_data             # really delete

Run it once a day (Phase 14: as a scheduled task on the server).
"""
from django.core.management.base import BaseCommand

from accounts.services.privacy import purge_old_data


class Command(BaseCommand):
    help = "Delete unclaimed resumes, inactive auto-created accounts, old audit entries and orphan files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Only count what would be deleted."
        )

    def handle(self, *args, dry_run, **options):
        counts = purge_old_data(dry_run=dry_run)
        verb = "Would delete" if dry_run else "Deleted"
        for name, number in counts.items():
            self.stdout.write(f"{verb} {number} {name}")
        if not dry_run:
            self.stdout.write(self.style.SUCCESS("Retention cleanup finished."))