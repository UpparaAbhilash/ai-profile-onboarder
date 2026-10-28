"""Tests for the jobs pipeline, audit log browser and CSV export."""
import csv
import io
from datetime import date, timedelta

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from jobs.models import Application, Job
from jobs.services.applications import apply_to_job, change_application_status
from profiles.models import Skill
from profiles.tests_status import PASSWORD, User, make_complete_profile

from .models import AuditLog
from .tests_dashboard import make_candidate, make_reviewer

PIPELINE_URL = reverse("dashboard:job_pipeline")
AUDIT_URL = reverse("dashboard:audit_log")
EXPORT_URL = reverse("dashboard:export_candidates")


def make_job(skills=("Python", "Docker"), **fields):
    data = {"title": "Python Developer", "company": "Example GmbH", "location": "Berlin",
            "description": "Build apps."}
    data.update(fields)
    job = Job.objects.create(**data)
    job.required_skills.set([Skill.objects.get_or_create(name=name)[0] for name in skills])
    return job


def read_csv(response):
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


class JobPipelineTests(TestCase):
    def setUp(self):
        self.reviewer = make_reviewer()
        self.client.force_login(self.reviewer)
        self.job = make_job()
        self.alina = make_candidate("alina@example.com", "Alina")   # Python, Django, MySQL
        self.boris = make_candidate("boris@example.com", "Boris")
        self.alina.skills.add(Skill.objects.get(name="Docker"))       # Alina: 100% match
        self.app_alina = apply_to_job(self.alina, self.job)
        self.app_boris = apply_to_job(self.boris, self.job)           # Boris: 50% match

    def test_pipeline_counts_applications_per_status(self):
        change_application_status(self.app_boris, Application.Status.UNDER_REVIEW, self.reviewer)
        job = self.client.get(PIPELINE_URL).context["jobs"][0]
        self.assertEqual((job.total, job.new, job.in_review), (2, 1, 1))

    def test_applicants_are_sorted_by_skill_match(self):
        content = self.client.get(reverse("dashboard:job_applicants", args=[self.job.pk])).content.decode()
        self.assertLess(content.index("Alina"), content.index("Boris"))
        self.assertIn("100%", content)
        self.assertIn("Missing: Docker", content)

    def test_applicants_can_be_filtered_by_status(self):
        change_application_status(self.app_boris, Application.Status.UNDER_REVIEW, self.reviewer)
        url = reverse("dashboard:job_applicants", args=[self.job.pk])
        response = self.client.get(url, {"status": "under_review"})
        self.assertContains(response, "Boris")
        self.assertNotContains(response, "Alina")

    def test_status_button_returns_to_the_pipeline_page(self):
        url = reverse("dashboard:job_applicants", args=[self.job.pk])
        response = self.client.post(
            reverse("dashboard:application_status", args=[self.app_alina.pk]),
            {"status": "under_review", "next": url},
        )
        self.assertRedirects(response, url)

    def test_external_next_url_is_ignored(self):
        response = self.client.post(
            reverse("dashboard:application_status", args=[self.app_alina.pk]),
            {"status": "under_review", "next": "https://evil.example.com/phishing"},
        )
        self.assertRedirects(response, reverse("dashboard:candidate_detail", args=[self.alina.pk]))


class AuditLogBrowserTests(TestCase):
    def setUp(self):
        self.reviewer = make_reviewer()
        self.client.force_login(self.reviewer)
        AuditLog.objects.create(actor=self.reviewer, action="test.recent")

    def entries(self, **params):
        return list(self.client.get(AUDIT_URL, params).context["page_obj"].object_list)

    def test_reviewer_can_open_audit_log(self):
        self.assertContains(self.client.get(AUDIT_URL), "test.recent")

    def test_dashboard_user_without_audit_permission_gets_403(self):
        user = User.objects.create_user(email="limited@example.com", password=PASSWORD)
        user.user_permissions.add(Permission.objects.get(codename="review_profile"))
        self.client.force_login(User.objects.get(pk=user.pk))
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 200)
        self.assertEqual(self.client.get(AUDIT_URL).status_code, 403)

    def test_filter_by_action(self):
        AuditLog.objects.create(actor=self.reviewer, action="test.other")
        actions = {entry.action for entry in self.entries(action="test.other")}
        self.assertEqual(actions, {"test.other"})

    def test_filter_by_date_excludes_older_entries(self):
        old = AuditLog.objects.create(actor=self.reviewer, action="test.old")
        AuditLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=10))
        since = (timezone.localdate() - timedelta(days=1)).isoformat()
        actions = {entry.action for entry in self.entries(date_from=since)}
        self.assertIn("test.recent", actions)
        self.assertNotIn("test.old", actions)

    def test_filter_by_user_email(self):
        other = User.objects.create_user(email="someone@example.com", password=PASSWORD)
        AuditLog.objects.create(actor=other, action="test.someone")
        actions = {entry.action for entry in self.entries(actor="someone@")}
        self.assertEqual(actions, {"test.someone"})


class CsvExportTests(TestCase):
    def setUp(self):
        self.reviewer = make_reviewer()
        self.client.force_login(self.reviewer)
        self.alina = make_candidate("alina@example.com", "Alina", date_of_birth=date(1998, 5, 14),
                                    aadhaar_last4="4321")
        self.boris = make_candidate("boris@example.com", "Boris")
        self.alina.skills.add(Skill.objects.create(name="Docker"))

    def test_export_contains_header_and_rows_but_no_sensitive_data(self):
        response = self.client.get(EXPORT_URL)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment", response["Content-Disposition"])
        rows = read_csv(response)
        self.assertEqual(rows[0][0], "Name")
        self.assertEqual(len(rows), 3)  # header + 2 candidates
        content = response.content.decode("utf-8-sig")
        for secret in ("1998", "4321", "491761234567", "alina@example.com"):
            self.assertNotIn(secret, content)

    def test_export_uses_the_same_filters_as_the_list(self):
        rows = read_csv(self.client.get(EXPORT_URL, {"skills": "docker"}))
        names = [row[0] for row in rows[1:]]
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith("Alina"))

    def test_export_is_written_to_the_audit_log(self):
        self.client.get(EXPORT_URL, {"skills": "python"})
        log = AuditLog.objects.get(action="candidates.exported")
        self.assertEqual(log.actor, self.reviewer)
        self.assertEqual(log.details["rows"], 2)
        self.assertEqual(log.details["filters"], {"skills": ["python"]})

    def test_spreadsheet_formulas_are_neutralised(self):
        make_candidate("evil@example.com", '=HYPERLINK("http://evil.example","Click")')
        names = [row[0] for row in read_csv(self.client.get(EXPORT_URL))[1:]]
        self.assertTrue(any(name.startswith("'=HYPERLINK") for name in names))
        self.assertFalse(any(name.startswith("=") for name in names))

    def test_candidates_cannot_export(self):
        candidate, _ = make_complete_profile("carl@example.com")
        self.client.force_login(candidate)
        self.assertEqual(self.client.get(EXPORT_URL).status_code, 403)