"""Tests for automatic accounts, set-password links, password reset and linking."""
import re
import shutil
import tempfile
from unittest.mock import patch
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from profiles.models import JobSeekerProfile
from profiles.tests_import import make_parsed_resume, parsed_fields
from resumes.tests import make_text_pdf, upload
from resumes.tests_ai import fake_client, make_resume_data

from .services.onboarding import onboard_from_resume

User = get_user_model()
PASSWORD = "S3cure-pass-123"
NEW_PASSWORD = "Brand-new-pass-456"
EMAIL = "asha.rao@example.com"  # the email inside parsed_fields() and SAMPLE_TEXT
LINK_RE = re.compile(r"https?://\S+/accounts/reset/\S+/")
TEMP_MEDIA_ROOT = tempfile.mkdtemp()


def link_path(message) -> str:
    """Return only the path of the first link in an email (test client needs a path)."""
    return urlparse(LINK_RE.search(message.body).group(0)).path


class OnboardingServiceTests(TestCase):
    def test_new_email_creates_account_without_password_and_sends_link(self):
        resume = make_parsed_resume(None)
        self.assertEqual(onboard_from_resume(resume), "created")

        user = User.objects.get(email=EMAIL)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.first_name, "Asha")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        self.assertRegex(mail.outbox[0].body, LINK_RE)
        resume.refresh_from_db()
        self.assertIsNone(resume.owner)  # not linked until the email is verified

    def test_existing_account_is_untouched_and_gets_no_email(self):
        User.objects.create_user(email=EMAIL, password=PASSWORD)
        self.assertEqual(onboard_from_resume(make_parsed_resume(None)), "exists")
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(User.objects.get(email=EMAIL).check_password(PASSWORD))

    def test_resume_without_email_creates_nothing(self):
        resume = make_parsed_resume(None, parsed_fields(email=None))
        self.assertEqual(onboard_from_resume(resume), "no_email")
        self.assertEqual(User.objects.count(), 0)

    def test_owned_resume_is_skipped(self):
        owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)
        self.assertEqual(onboard_from_resume(make_parsed_resume(owner)), "skipped")
        self.assertEqual(len(mail.outbox), 0)


class SetPasswordFlowTests(TestCase):
    def start_onboarding(self):
        resume = make_parsed_resume(None)
        onboard_from_resume(resume)
        return resume, link_path(mail.outbox[0])

    def set_password(self, path):
        response = self.client.get(path, follow=True)  # Django moves the token into the session
        self.assertContains(response, "new_password1")
        form_url = response.redirect_chain[-1][0]
        return self.client.post(
            form_url, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        )

    def test_full_onboarding_flow_logs_in_and_links_resume(self):
        resume, path = self.start_onboarding()
        response = self.set_password(path)

        self.assertRedirects(response, reverse("profiles:me"))
        user = User.objects.get(email=EMAIL)
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        resume.refresh_from_db()
        self.assertEqual(resume.owner, user)
        self.assertEqual(JobSeekerProfile.objects.get(user=user).first_name, "Asha")

    def test_link_works_only_once(self):
        _, path = self.start_onboarding()
        self.set_password(path)
        self.client.logout()
        response = self.client.get(path, follow=True)
        self.assertContains(response, "invalid or has already been used")

    def test_tampered_token_is_rejected(self):
        _, path = self.start_onboarding()
        broken = path.rstrip("/").rsplit("/", 1)[0] + "/wrong-token/"
        response = self.client.get(broken, follow=True)
        self.assertContains(response, "invalid or has already been used")


class PasswordResetTests(TestCase):
    def test_reset_works_for_account_that_never_set_a_password(self):
        User.objects.create_user(email="new@example.com")
        response = self.client.post(reverse("accounts:password_reset"), {"email": "new@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertRegex(mail.outbox[0].body, LINK_RE)

    def test_unknown_email_gets_same_response_and_no_email(self):
        response = self.client.post(reverse("accounts:password_reset"), {"email": "nobody@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_login_page_links_to_password_reset(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, reverse("accounts:password_reset"))


class LinkOnLoginTests(TestCase):
    def test_login_links_waiting_resume_and_creates_profile(self):
        user = User.objects.create_user(email=EMAIL, password=PASSWORD)
        resume = make_parsed_resume(None)
        self.client.post(reverse("accounts:login"), {"username": EMAIL, "password": PASSWORD})
        resume.refresh_from_db()
        self.assertEqual(resume.owner, user)
        self.assertTrue(JobSeekerProfile.objects.filter(user=user).exists())

    def test_resume_with_a_different_email_is_not_linked(self):
        user = User.objects.create_user(email="ravi@example.com", password=PASSWORD)
        resume = make_parsed_resume(None)  # belongs to asha.rao@example.com
        self.client.force_login(user)
        resume.refresh_from_db()
        self.assertIsNone(resume.owner)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT, OPENAI_MODEL="test-model", OPENAI_API_KEY="")
class AnonymousUploadTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    @patch("resumes.services.ai_parser.get_client")
    def test_anonymous_upload_creates_account_and_sends_email(self, mock_get_client):
        mock_get_client.return_value = fake_client(make_resume_data())
        response = self.client.post(
            reverse("resumes:upload"), {"file": upload(make_text_pdf())}, follow=True
        )
        self.assertContains(response, "Check your inbox")
        self.assertFalse(User.objects.get(email=EMAIL).has_usable_password())
        self.assertEqual(len(mail.outbox), 1)

    @patch("resumes.services.ai_parser.get_client")
    def test_logged_in_upload_creates_no_new_account(self, mock_get_client):
        mock_get_client.return_value = fake_client(make_resume_data())
        owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)
        self.client.force_login(owner)
        self.client.post(reverse("resumes:upload"), {"file": upload(make_text_pdf())})
        self.assertFalse(User.objects.filter(email=EMAIL).exists())
        self.assertEqual(len(mail.outbox), 0)