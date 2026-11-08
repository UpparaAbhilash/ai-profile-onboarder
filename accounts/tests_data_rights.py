"""Tests for the user's data rights: privacy page, data export, account deletion."""
import json
import shutil
import tempfile

from django.test import TestCase, override_settings
from django.urls import reverse

from dashboard.models import AuditLog
from jobs.services.applications import apply_to_job
from jobs.test_applications import make_job
from profiles.tests_status import PASSWORD, User, make_complete_profile
from resumes.models import Resume
from resumes.services.pdf_validation import validate_resume_file
from resumes.services.resume_intake import create_resume
from resumes.tests import make_text_pdf, upload

TEMP_MEDIA_ROOT = tempfile.mkdtemp()
PRIVACY_URL = reverse("accounts:privacy")
EXPORT_URL = reverse("accounts:my_data")
DELETE_URL = reverse("accounts:delete_account")


class PrivacyPageTests(TestCase):
    def test_privacy_page_is_public_and_explains_retention(self):
        response = self.client.get(PRIVACY_URL)
        self.assertContains(response, "30 days")
        self.assertContains(response, "365 days")
        self.assertNotContains(response, EXPORT_URL)  # buttons only for logged-in users

    def test_footer_links_to_privacy_page(self):
        self.assertContains(self.client.get("/"), PRIVACY_URL)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class DataRightsTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user, self.profile = make_complete_profile("asha@example.com")
        self.resume = create_resume(
            validate_resume_file(upload(make_text_pdf())), "asha-cv.pdf", owner=self.user
        )
        apply_to_job(self.profile, make_job(title="Django Developer"))
        self.other, _ = make_complete_profile("ravi@example.com")
        self.client.force_login(self.user)

    # ---- Download my data ------------------------------------------------
    def test_export_requires_login(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(EXPORT_URL), f"{reverse('accounts:login')}?next={EXPORT_URL}"
        )

    def test_export_contains_all_own_data_as_json_download(self):
        response = self.client.get(EXPORT_URL)
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        data = json.loads(response.content)
        self.assertEqual(data["account"]["email"], "asha@example.com")
        self.assertEqual(data["profile"]["phone"], "+491761234567")
        self.assertIn("Python", data["profile"]["skills"])
        self.assertEqual(data["applications"][0]["job_title"], "Django Developer")
        self.assertEqual(data["resumes"][0]["original_filename"], "asha-cv.pdf")

    def test_export_contains_no_password_hash_and_no_other_users(self):
        content = self.client.get(EXPORT_URL).content.decode()
        self.assertNotIn(self.user.password, content)
        self.assertNotIn("ravi@example.com", content)

    def test_export_is_audited(self):
        self.client.get(EXPORT_URL)
        self.assertTrue(AuditLog.objects.filter(action="data.exported", actor=self.user).exists())

    # ---- Delete my account -------------------------------------------------
    def delete(self, password=PASSWORD, confirm=True):
        data = {"password": password}
        if confirm:
            data["confirm"] = "on"
        with self.captureOnCommitCallbacks(execute=True):  # PDF files are removed after commit
            return self.client.post(DELETE_URL, data)

    def test_wrong_password_deletes_nothing(self):
        response = self.delete(password="not-my-password")
        self.assertContains(response, "The password is not correct.")
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_confirmation_checkbox_is_required(self):
        self.delete(confirm=False)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_correct_password_deletes_everything_and_logs_out(self):
        response = self.delete()
        self.assertRedirects(response, reverse("home"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Resume.objects.filter(pk=self.resume.pk).exists())
        self.assertFalse(self.resume.file.storage.exists(self.resume.file.name))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(User.objects.filter(pk=self.other.pk).exists())  # nobody else affected

    def test_superuser_cannot_delete_themselves_here(self):
        admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        self.client.force_login(admin)
        response = self.delete()
        self.assertRedirects(response, PRIVACY_URL)
        self.assertTrue(User.objects.filter(pk=admin.pk).exists())