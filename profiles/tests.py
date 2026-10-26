from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import JobSeekerProfile, Project, Skill

User = get_user_model()


class ProfileModelTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(email="asha@example.com")
        self.profile = JobSeekerProfile.objects.create(user=user, first_name="Asha")

    def test_aadhaar_is_masked(self):
        self.profile.aadhaar_last4 = "1234"
        self.assertEqual(self.profile.aadhaar_masked, "XXXX-XXXX-1234")

    def test_experience_months_converted_to_years(self):
        self.profile.total_experience_months = 30
        self.assertEqual(self.profile.total_experience_years, 2.5)

    def test_score_above_100_is_rejected_by_database(self):
        self.profile.score = 101
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.profile.save()

    def test_project_cannot_end_before_it_starts(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Project.objects.create(
                profile=self.profile,
                title="Broken dates",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 1, 1),
            )

    def test_skill_names_are_unique_ignoring_case(self):
        Skill.objects.create(name="Python")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Skill.objects.create(name="python")