"""Tests for job browsing, applying, withdrawing and reviewing applications."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from dashboard.models import AuditLog
from profiles.models import JobSeekerProfile, Skill
from profiles.tests_status import PASSWORD, User, make_complete_profile

from .models import Application, Job
from .services.applications import (
    ApplicationError,
    apply_to_job,
    change_application_status,
    skill_match,
    withdraw_application,
)

AppStatus = Application.Status


def make_job(**overrides):
    data = {"title": "Python Developer", "company": "Example GmbH", "location": "Berlin",
            "description": "Build Django apps."}
    data.update(overrides)
    skills = data.pop("skills", ["Python", "Django", "Docker"])
    job = Job.objects.create(**data)
    job.required_skills.set([Skill.objects.get_or_create(name=name)[0] for name in skills])
    return job


class JobBrowsingTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()  # skills: Python, Django, MySQL
        self.job = make_job()

    def test_job_list_is_public_and_hides_inactive_jobs(self):
        make_job(title="Old closed job", is_active=False)
        response = self.client.get(reverse("jobs:list"))
        self.assertContains(response, "Python Developer")
        self.assertNotContains(response, "Old closed job")

    def test_search_finds_jobs_by_skill(self):
        make_job(title="Data Analyst", skills=["SQL"])
        response = self.client.get(reverse("jobs:list"), {"q": "docker"})
        self.assertContains(response, "Python Developer")
        self.assertNotContains(response, "Data Analyst")

    def test_skill_match_ignores_case(self):
        match = skill_match(self.profile, self.job)
        self.assertEqual(match["matched"], ["Django", "Python"])
        self.assertEqual(match["missing"], ["Docker"])
        self.assertEqual(match["percent"], 67)

    def test_job_detail_shows_skill_match_to_candidate(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("jobs:detail", args=[self.job.pk]))
        self.assertContains(response, "Skill match: 67%")

    def test_inactive_job_gives_404(self):
        self.job.is_active = False
        self.job.save()
        self.assertEqual(self.client.get(reverse("jobs:detail", args=[self.job.pk])).status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse("jobs:apply", args=[self.job.pk])).status_code, 404)


class ApplyTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()
        self.job = make_job()
        self.url = reverse("jobs:apply", args=[self.job.pk])

    def test_apply_requires_login_and_post(self):
        self.assertRedirects(self.client.post(self.url), f"{reverse('accounts:login')}?next={self.url}")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_candidate_can_apply(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"cover_note": "I would love to join."})
        self.assertRedirects(response, reverse("jobs:my_applications"))
        application = Application.objects.get()
        self.assertEqual(application.status, AppStatus.SUBMITTED)
        self.assertEqual(application.cover_note, "I would love to join.")
        self.assertTrue(AuditLog.objects.filter(action="application.submitted").exists())

    def test_duplicate_application_is_rejected(self):
        self.client.force_login(self.user)
        self.client.post(self.url)
        response = self.client.post(self.url, follow=True)
        self.assertContains(response, "already applied")
        self.assertEqual(Application.objects.count(), 1)

    def test_incomplete_profile_cannot_apply(self):
        self.profile.phone = ""
        self.profile.save()
        with self.assertRaisesMessage(ApplicationError, "complete your profile"):
            apply_to_job(self.profile, self.job)
        self.assertEqual(Application.objects.count(), 0)

    def test_not_interested_candidate_cannot_apply(self):
        self.profile.status = JobSeekerProfile.Status.NOT_INTERESTED
        self.profile.save()
        with self.assertRaisesMessage(ApplicationError, "Not Interested"):
            apply_to_job(self.profile, self.job)

    def test_user_without_profile_is_sent_to_upload(self):
        other = User.objects.create_user(email="new@example.com", password=PASSWORD)
        self.client.force_login(other)
        self.assertRedirects(self.client.post(self.url), reverse("resumes:upload"))

    def test_too_long_cover_note_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"cover_note": "x" * 2001}, follow=True)
        self.assertContains(response, "too long")
        self.assertEqual(Application.objects.count(), 0)


class MyApplicationsTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()
        self.job = make_job()
        self.application = apply_to_job(self.profile, self.job)

    def test_list_shows_only_own_applications(self):
        _, other_profile = make_complete_profile("ravi@example.com")
        apply_to_job(other_profile, make_job(title="Secret job", skills=["Python"]))
        self.client.force_login(self.user)
        response = self.client.get(reverse("jobs:my_applications"))
        self.assertContains(response, "Python Developer")
        self.assertNotContains(response, "Secret job")

    def test_candidate_can_withdraw(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("jobs:withdraw", args=[self.application.pk]))
        self.assertRedirects(response, reverse("jobs:my_applications"))
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, AppStatus.WITHDRAWN)
        self.assertTrue(AuditLog.objects.filter(action="application.withdrawn").exists())

    def test_cannot_withdraw_someone_elses_application(self):
        other, _ = make_complete_profile("ravi@example.com")
        self.client.force_login(other)
        response = self.client.post(reverse("jobs:withdraw", args=[self.application.pk]))
        self.assertEqual(response.status_code, 404)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, AppStatus.SUBMITTED)

    def test_apply_again_after_withdrawing_reuses_the_application(self):
        withdraw_application(self.application, self.user)
        apply_to_job(self.profile, self.job, "Second try")
        self.assertEqual(Application.objects.count(), 1)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, AppStatus.SUBMITTED)
        self.assertEqual(self.application.cover_note, "Second try")

    def test_shortlisted_application_cannot_be_withdrawn(self):
        self.application.status = AppStatus.SHORTLISTED
        self.application.save()
        with self.assertRaisesMessage(ApplicationError, "can no longer be withdrawn"):
            withdraw_application(self.application, self.user)


class ReviewTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()
        self.job = make_job()
        self.application = apply_to_job(self.profile, self.job)
        self.admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)

    def test_reviewer_moves_application_forward(self):
        change_application_status(self.application, AppStatus.UNDER_REVIEW, self.admin)
        change_application_status(self.application, AppStatus.SHORTLISTED, self.admin)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, AppStatus.SHORTLISTED)
        self.assertEqual(AuditLog.objects.filter(action="application.status_changed").count(), 2)

    def test_skipping_a_step_is_rejected(self):
        with self.assertRaisesMessage(ApplicationError, "cannot change"):
            change_application_status(self.application, AppStatus.SHORTLISTED, self.admin)

    def test_candidate_cannot_review_applications(self):
        with self.assertRaisesMessage(ApplicationError, "permission"):
            change_application_status(self.application, AppStatus.UNDER_REVIEW, self.user)

    def test_withdrawn_application_cannot_be_reviewed(self):
        withdraw_application(self.application, self.user)
        with self.assertRaisesMessage(ApplicationError, "cannot change"):
            change_application_status(self.application, AppStatus.UNDER_REVIEW, self.admin)

    def test_admin_action_marks_under_review(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("admin:jobs_application_changelist"),
            {"action": "mark_under_review", "_selected_action": [str(self.application.pk)]},
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, AppStatus.UNDER_REVIEW)

    def test_applications_cannot_be_added_in_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin:jobs_application_add")).status_code, 403)


class SeedJobsTests(TestCase):
    def test_seed_jobs_is_safe_to_run_twice(self):
        call_command("seed_jobs", stdout=StringIO())
        call_command("seed_jobs", stdout=StringIO())
        self.assertEqual(Job.objects.count(), 6)
        self.assertEqual(Job.objects.get(title="Werkstudent GenAI Engineering").required_skills.count(), 4)