"""Tests for job recommendations (Phase 16A). No AI is involved."""
from django.test import TestCase
from django.urls import reverse

from profiles.models import JobSeekerProfile
from profiles.tests_status import PASSWORD, User, make_complete_profile

from .models import Application, Job
from .services.recommendations import recommend_jobs
from .test_applications import make_job

RECOMMENDED_URL = reverse("jobs:recommended")


class RecommendJobsServiceTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()  # skills: Python, Django, MySQL

    def titles(self, **kwargs):
        return [job.title for job, match in recommend_jobs(self.profile, **kwargs)]

    def test_best_match_comes_first(self):
        make_job(title="Good fit", skills=["Python", "Django", "Docker"])     # 67%
        make_job(title="Perfect fit", skills=["Python", "Django", "MySQL"])   # 100%
        self.assertEqual(self.titles(), ["Perfect fit", "Good fit"])

    def test_weak_and_unrelated_jobs_are_hidden(self):
        make_job(title="Weak fit", skills=["Python", "Java", "Go"])  # 33%: below 50%
        make_job(title="Unrelated", skills=["Photoshop"])            # 0%
        self.assertEqual(self.titles(), [])

    def test_match_details_are_returned(self):
        make_job(skills=["Python", "Docker"])
        job, match = recommend_jobs(self.profile)[0]
        self.assertEqual(match["percent"], 50)
        self.assertEqual(match["matched"], ["Python"])
        self.assertEqual(match["missing"], ["Docker"])

    def test_closed_jobs_and_jobs_without_skills_are_skipped(self):
        make_job(title="Closed", skills=["Python"], is_active=False)
        make_job(title="No skills listed", skills=[])
        self.assertEqual(self.titles(), [])

    def test_jobs_already_applied_for_are_skipped(self):
        job = make_job(title="Applied", skills=["Python"])
        Application.objects.create(job=job, candidate=self.profile)
        self.assertEqual(self.titles(), [])

    def test_withdrawn_job_can_be_recommended_again(self):
        job = make_job(title="Withdrawn", skills=["Python"])
        Application.objects.create(job=job, candidate=self.profile, status=Application.Status.WITHDRAWN)
        self.assertEqual(self.titles(), ["Withdrawn"])

    def test_skills_match_without_case(self):
        make_job(title="Lower case", skills=["python"])
        self.assertEqual(self.titles(), ["Lower case"])

    def test_result_is_limited(self):
        for number in range(7):
            make_job(title=f"Job {number}", skills=["Python"])
        self.assertEqual(len(self.titles()), 5)
        self.assertEqual(len(self.titles(limit=2)), 2)

    def test_other_candidates_applications_do_not_matter(self):
        job = make_job(title="Popular", skills=["Python"])
        _, other_profile = make_complete_profile(email="other@example.com")
        Application.objects.create(job=job, candidate=other_profile)
        self.assertEqual(self.titles(), ["Popular"])

    def test_no_profile_gives_no_recommendations(self):
        make_job(skills=["Python"])
        self.assertEqual(recommend_jobs(None), [])


class RecommendedViewTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()

    def test_login_is_required(self):
        response = self.client.get(RECOMMENDED_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_user_without_profile_is_sent_to_upload(self):
        user = User.objects.create_user(email="new@example.com", password=PASSWORD)
        self.client.force_login(user)
        self.assertRedirects(self.client.get(RECOMMENDED_URL), reverse("resumes:upload"))

    def test_page_shows_matching_jobs_with_percent(self):
        job = make_job(title="Django Developer", skills=["Python", "Django"])
        self.client.force_login(self.user)
        response = self.client.get(RECOMMENDED_URL)
        self.assertContains(response, "Django Developer")
        self.assertContains(response, "100% match")
        self.assertContains(response, reverse("jobs:detail", args=[job.pk]))

    def test_page_never_applies(self):
        make_job(skills=["Python"])
        self.client.force_login(self.user)
        self.client.get(RECOMMENDED_URL)
        self.assertEqual(Application.objects.count(), 0)

    def test_empty_state_when_nothing_matches(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(RECOMMENDED_URL), "No matching jobs yet")

    def test_not_interested_candidate_sees_hint(self):
        JobSeekerProfile.objects.filter(pk=self.profile.pk).update(
            status=JobSeekerProfile.Status.NOT_INTERESTED
        )
        self.client.force_login(self.user)
        self.assertContains(self.client.get(RECOMMENDED_URL), "Not Interested")

    def test_post_is_not_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(RECOMMENDED_URL).status_code, 405)

    def test_job_list_links_to_recommendations_when_logged_in(self):
        self.assertNotContains(self.client.get(reverse("jobs:list")), RECOMMENDED_URL)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("jobs:list")), RECOMMENDED_URL)
