"""Tests for shared UI components: status colours, empty states, mobile tables."""
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from dashboard.tests_dashboard import make_reviewer
from jobs.services.applications import apply_to_job
from jobs.test_applications import make_job
from profiles.tests_status import make_complete_profile

from .templatetags.ui import status_color


class StatusColorTests(SimpleTestCase):
    def test_each_status_has_one_colour(self):
        self.assertEqual(status_color("shortlisted"), "success")
        self.assertEqual(status_color("rejected"), "danger")
        self.assertEqual(status_color("open_to_work"), "success")
        self.assertEqual(status_color("parsed"), "success")

    def test_unknown_status_falls_back_to_secondary(self):
        self.assertEqual(status_color("something_new"), "secondary")


class EmptyStateTests(TestCase):
    def test_no_applications_shows_next_step(self):
        user, _ = make_complete_profile()
        self.client.force_login(user)
        response = self.client.get(reverse("jobs:my_applications"))
        self.assertContains(response, "No applications yet")
        self.assertContains(response, f'href="{reverse("jobs:list")}"')

    def test_search_without_results_offers_to_show_all_jobs(self):
        make_job(title="Python Developer")
        response = self.client.get(reverse("jobs:list"), {"q": "astronaut"})
        self.assertContains(response, "No jobs match your search")
        self.assertContains(response, "Show all jobs")

    def test_candidate_filters_without_results_offer_reset(self):
        self.client.force_login(make_reviewer())
        response = self.client.get(reverse("dashboard:candidate_list"), {"city": "Atlantis"})
        self.assertContains(response, "No candidates match these filters")
        self.assertContains(response, "Reset filters")


class MobileTableTests(TestCase):
    def test_application_rows_have_labels_and_status_colour(self):
        user, profile = make_complete_profile()
        apply_to_job(profile, make_job())
        self.client.force_login(user)
        response = self.client.get(reverse("jobs:my_applications"))
        self.assertContains(response, 'class="table align-middle table-stack"')
        self.assertContains(response, 'data-label="Status"')
        self.assertContains(response, "badge text-bg-primary")  # "submitted" is primary