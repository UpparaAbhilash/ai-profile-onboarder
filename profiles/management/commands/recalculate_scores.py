"""Recalculate the stored score of every profile.

Usage: python manage.py recalculate_scores
Run it after changing the scoring formula, or for profiles created before scoring existed.
"""
from django.core.management.base import BaseCommand

from profiles.models import JobSeekerProfile
from profiles.services.scoring import update_profile_score


class Command(BaseCommand):
    help = "Recalculate the score of every job seeker profile."

    def handle(self, *args, **options):
        count = 0
        for profile in JobSeekerProfile.objects.prefetch_related("skills", "projects", "achievements"):
            update_profile_score(profile)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Recalculated {count} profile score(s)."))