"""Tests for the reviewer dashboard: access control, search filters and review actions."""
from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from jobs.models import Application, Job
from jobs.services.applications import apply_to_job
from profiles.models import JobSeekerProfile, Skill
from profiles.tests_status import PASSWORD, User, make_complete_profile

from .models import AuditLog

LIST_URL = reverse("dashboard:candidate_list")


def make_reviewer(email="reviewer@example.com"):
    call_command("setup_roles", stdout=StringIO())
    user = User.objects.create_user(email=email, password=PASSWORD)
    user.groups.add(Group.objects.get(name="Reviewer"))
    return User.objects.get(pk=user.pk)  # fresh object: permissions are cached


def make_candidate(email, first_name, **fields):
    _, profile = make_complete_profile(email)
    profile.first_name = first_name
    for name, value in fields.items():
        setattr(profile, name, value)
    profile.save()
    return profile


class AccessTests(TestCase):
    def test_anonymous_user_is_sent_to_login(self):
        url = reverse("dashboard:home")
        self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_candidate_gets_403(self):
        user, _ = make_complete_profile()
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 403)
        self.assertEqual(self.client.get(LIST_URL).status_code, 403)

    def test_staff_without_reviewer_permission_gets_403(self):
        staff = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 403)

    def test_reviewer_can_open_dashboard_but_not_admin(self):
        self.client.force_login(make_reviewer())
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 200)
        self.assertEqual(self.client.get(LIST_URL).status_code, 200)
        admin_response = self.client.get(reverse("admin:index"))
        self.assertEqual(admin_response.status_code, 302)  # not staff -> admin login page

    def test_setup_roles_adds_user_to_group(self):
        user = User.objects.create_user(email="new.reviewer@example.com", password=PASSWORD)
        call_command("setup_roles", "--add", "new.reviewer@example.com", stdout=StringIO())
        self.assertTrue(User.objects.get(pk=user.pk).has_perm("profiles.review_profile"))


class SearchTests(TestCase):
    def setUp(self):
        self.client.force_login(make_reviewer())
        self.alina = make_candidate("alina@example.com", "Alina", current_city="Munich",
                                    total_experience_months=12)
        self.boris = make_candidate("boris@example.com", "Boris", current_city="Hamburg",
                                    preferred_locations=["Hamburg"], total_experience_months=60)
        self.alina.skills.add(Skill.objects.create(name="Docker"))

    def search(self, **params):
        return self.client.get(LIST_URL, params)

    def test_skill_filter_requires_all_skills(self):
        response = self.search(skills="python, docker")
        self.assertContains(response, "Alina")
        self.assertNotContains(response, "Boris")

    def test_city_filter_includes_preferred_locations(self):
        response = self.search(city="berlin")  # Alina lives in Munich but prefers Berlin
        self.assertContains(response, "Alina")
        self.assertNotContains(response, "Boris")

    def test_status_filter(self):
        self.boris.status = JobSeekerProfile.Status.OPEN_TO_WORK
        self.boris.save()
        response = self.search(status="open_to_work")
        self.assertContains(response, "Boris")
        self.assertNotContains(response, "Alina")

    def test_minimum_experience_filter(self):
        response = self.search(min_years=3)
        self.assertContains(response, "Boris")
        self.assertNotContains(response, "Alina")

    def test_minimum_score_filter(self):
        JobSeekerProfile.objects.filter(pk=self.alina.pk).update(score=40)
        JobSeekerProfile.objects.filter(pk=self.boris.pk).update(score=80)
        response = self.search(min_score=50)
        self.assertContains(response, "Boris")
        self.assertNotContains(response, "Alina")

    def test_text_search_by_email(self):
        response = self.search(q="boris@")
        self.assertContains(response, "Boris")
        self.assertNotContains(response, "Alina")

    def test_sort_by_score(self):
        JobSeekerProfile.objects.filter(pk=self.alina.pk).update(score=30)
        JobSeekerProfile.objects.filter(pk=self.boris.pk).update(score=90)
        content = self.search(sort="score").content.decode()
        self.assertLess(content.index("Boris"), content.index("Alina"))

    def test_invalid_experience_range_shows_error(self):
        response = self.search(min_years=5, max_years=2)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cannot be smaller than minimum")


class CandidateDetailTests(TestCase):
    def setUp(self):
        self.reviewer = make_reviewer()
        self.client.force_login(self.reviewer)
        self.profile = make_candidate("alina@example.com", "Alina")
        self.url = reverse("dashboard:candidate_detail", args=[self.profile.pk])

    def test_detail_page_is_shown_and_access_is_logged(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Alina")
        self.assertContains(response, "Score breakdown")
        log = AuditLog.objects.get(action="profile.viewed")
        self.assertEqual(log.actor, self.reviewer)
        self.assertEqual(log.target, self.profile)

    def test_reviewer_marks_profile_reviewed_with_note(self):
        response = self.client.post(
            reverse("dashboard:review_candidate", args=[self.profile.pk]), {"note": "Strong profile."}
        )
        self.assertRedirects(response, self.url)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, JobSeekerProfile.Status.REVIEWED)
        self.assertEqual(self.profile.status_history.first().note, "Strong profile.")

    def test_review_is_refused_when_candidate_already_chose(self):
        self.profile.status = JobSeekerProfile.Status.OPEN_TO_WORK
        self.profile.save()
        response = self.client.post(
            reverse("dashboard:review_candidate", args=[self.profile.pk]), follow=True
        )
        self.assertContains(response, "cannot change")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, JobSeekerProfile.Status.OPEN_TO_WORK)

    def test_reviewer_moves_application_forward(self):
        job = Job.objects.create(title="Python Developer", company="Example GmbH",
                                 location="Berlin", description="Build apps.")
        application = apply_to_job(self.profile, job)
        response = self.client.post(
            reverse("dashboard:application_status", args=[application.pk]), {"status": "under_review"}
        )
        self.assertRedirects(response, self.url)
        application.refresh_from_db()
        self.assertEqual(application.status, Application.Status.UNDER_REVIEW)