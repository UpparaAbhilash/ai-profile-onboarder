from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from profiles.models import JobSeekerProfile

from .models import Application, Job

User = get_user_model()


class ApplicationTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(email="ravi@example.com")
        self.profile = JobSeekerProfile.objects.create(user=user)
        self.job = Job.objects.create(
            title="Python Developer", company="Acme", location="Berlin", description="..."
        )

    def test_candidate_can_apply_once(self):
        Application.objects.create(job=self.job, candidate=self.profile)
        self.assertEqual(self.profile.applications.count(), 1)

    def test_duplicate_application_is_rejected_by_database(self):
        Application.objects.create(job=self.job, candidate=self.profile)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Application.objects.create(job=self.job, candidate=self.profile)

    def test_same_candidate_can_apply_to_different_jobs(self):
        other_job = Job.objects.create(
            title="Data Analyst", company="Acme", location="Munich", description="..."
        )
        Application.objects.create(job=self.job, candidate=self.profile)
        Application.objects.create(job=other_job, candidate=self.profile)
        self.assertEqual(self.profile.applications.count(), 2)