"""Tests for background resume parsing. No Redis and no OpenAI: tasks run eagerly
in the test process and a fake AI client is used."""
import shutil
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import openai
from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from kombu.exceptions import OperationalError

from profiles.models import JobSeekerProfile

from .models import Resume
from .services.ai_parser import ResumeParsingError
from .services.pdf_validation import validate_resume_file
from .services.resume_intake import create_resume
from .tasks import QUEUE_ERROR_MESSAGE, RETRY_DELAYS, parse_resume_task
from .tests import make_image_only_pdf, make_text_pdf, upload
from .tests_ai import REQUEST, fake_client, make_resume_data

User = get_user_model()
TEMP_MEDIA_ROOT = tempfile.mkdtemp()
UPLOAD_URL = reverse("resumes:upload")
TIMEOUT = openai.APITimeoutError(request=REQUEST)  # a temporary, retryable AI error


def ai_answer():
    return SimpleNamespace(output_parsed=make_resume_data())


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT, OPENAI_MODEL="test-model", OPENAI_API_KEY="")
class ParseResumeTaskTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def make_resume(self, pdf_bytes=None, owner=None):
        validated = validate_resume_file(upload(pdf_bytes or make_text_pdf()))
        return create_resume(validated, "resume.pdf", owner=owner)

    def run_task(self, resume_id):
        return parse_resume_task.delay(resume_id).get()

    @patch("resumes.services.ai_parser.get_client")
    def test_anonymous_resume_is_parsed_and_account_created(self, mock_get_client):
        mock_get_client.return_value = fake_client(make_resume_data())
        resume = self.make_resume()
        self.assertEqual(self.run_task(resume.pk), "parsed:created")
        resume.refresh_from_db()
        self.assertEqual(resume.status, Resume.Status.PARSED)
        self.assertEqual(len(mail.outbox), 1)

    @patch("resumes.services.ai_parser.get_client")
    def test_owned_resume_fills_profile_and_sends_no_email(self, mock_get_client):
        mock_get_client.return_value = fake_client(make_resume_data())
        owner = User.objects.create_user(email="owner@example.com", password="S3cure-pass-123")
        resume = self.make_resume(owner=owner)
        self.assertEqual(self.run_task(resume.pk), "parsed")
        self.assertTrue(JobSeekerProfile.objects.filter(user=owner).exists())
        self.assertEqual(len(mail.outbox), 0)

    @patch("resumes.services.ai_parser.get_client")
    def test_running_twice_calls_the_ai_only_once(self, mock_get_client):
        client = fake_client(make_resume_data())
        mock_get_client.return_value = client
        resume = self.make_resume()
        self.run_task(resume.pk)
        self.assertEqual(self.run_task(resume.pk), "parsed")
        self.assertEqual(client.responses.parse.call_count, 1)
        self.assertEqual(len(mail.outbox), 1)

    @patch("resumes.services.ai_parser.get_client")
    def test_temporary_error_schedules_retry_then_succeeds(self, mock_get_client):
        client = fake_client()
        client.responses.parse.side_effect = [TIMEOUT, ai_answer()]
        mock_get_client.return_value = client
        resume = self.make_resume()

        # Attempt 1: temporary error -> Celery is asked to try again in 30 seconds.
        with self.assertRaises(Retry) as cm:
            parse_resume_task.apply(args=[resume.pk])
        self.assertEqual(cm.exception.when, RETRY_DELAYS[0])
        resume.refresh_from_db()
        self.assertEqual(resume.error_message, "")  # the page keeps showing "analysing"

        # Attempt 2 (what the worker runs 30 seconds later): the AI answers.
        result = parse_resume_task.apply(args=[resume.pk], retries=1).get()
        self.assertEqual(result, "parsed:created")
        self.assertEqual(client.responses.parse.call_count, 2)

    @patch("resumes.services.ai_parser.get_client")
    def test_last_attempt_gives_up_and_saves_message(self, mock_get_client):
        client = fake_client(error=TIMEOUT)
        mock_get_client.return_value = client
        resume = self.make_resume()
        # retries=3 simulates the 4th and final attempt: no more retries are allowed.
        result = parse_resume_task.apply(args=[resume.pk], retries=len(RETRY_DELAYS)).get()
        self.assertEqual(result, "ai_failed")
        resume.refresh_from_db()
        self.assertEqual(resume.status, Resume.Status.EXTRACTED)  # can still be re-parsed later
        self.assertIn("timed out", resume.error_message)

    @patch("resumes.services.ai_parser.get_client")
    def test_permanent_error_is_not_retried(self, mock_get_client):
        mock_get_client.side_effect = ResumeParsingError("The AI service rejected the API key.")
        resume = self.make_resume()
        self.assertEqual(self.run_task(resume.pk), "ai_failed")
        self.assertEqual(mock_get_client.call_count, 1)
        resume.refresh_from_db()
        self.assertIn("rejected the API key", resume.error_message)

    def test_scanned_resume_is_skipped(self):
        resume = self.make_resume(make_image_only_pdf())
        self.assertEqual(self.run_task(resume.pk), Resume.Status.FAILED)

    def test_missing_resume_is_ignored(self):
        self.assertEqual(self.run_task(999999), "missing")


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT, OPENAI_MODEL="test-model", OPENAI_API_KEY="")
class BackgroundUploadViewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def post_upload(self, **kwargs):
        return self.client.post(UPLOAD_URL, {"file": upload(make_text_pdf())}, **kwargs)

    def detail(self, resume):
        return self.client.get(reverse("resumes:detail", args=[resume.pk]))

    def test_upload_answers_at_once_and_queues_one_task(self):
        with self.captureOnCommitCallbacks() as callbacks:  # queued, but NOT run
            response = self.post_upload(follow=True)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(Resume.objects.get().status, Resume.Status.EXTRACTED)
        self.assertContains(response, "Analysing your resume")
        self.assertContains(response, 'http-equiv="refresh"')

    @patch("resumes.services.ai_parser.get_client")
    def test_page_stops_refreshing_when_parsed(self, mock_get_client):
        mock_get_client.return_value = fake_client(make_resume_data())
        with self.captureOnCommitCallbacks(execute=True):
            self.post_upload()
        response = self.detail(Resume.objects.get())
        self.assertContains(response, "Extracted details")
        self.assertNotContains(response, 'http-equiv="refresh"')

    @patch("resumes.services.ai_parser.get_client")
    def test_resume_without_email_shows_warning(self, mock_get_client):
        mock_get_client.return_value = fake_client(make_resume_data(email=None))
        with self.captureOnCommitCallbacks(execute=True):
            self.post_upload()
        response = self.detail(Resume.objects.get())
        self.assertContains(response, "could not find a valid email address")
        self.assertEqual(User.objects.count(), 0)

    @patch("resumes.tasks.parse_resume_task")
    def test_upload_still_works_when_redis_is_down(self, mock_task):
        mock_task.delay.side_effect = OperationalError("Redis is down")
        with self.assertLogs("resumes.tasks", level="ERROR"):  # expected error, logged quietly
            with self.captureOnCommitCallbacks(execute=True):
                response = self.post_upload()
        resume = Resume.objects.get()
        self.assertRedirects(response, reverse("resumes:detail", args=[resume.pk]))
        self.assertEqual(resume.error_message, QUEUE_ERROR_MESSAGE)
        self.assertNotContains(self.detail(resume), 'http-equiv="refresh"')

    def test_page_stops_refreshing_after_timeout(self):
        self.post_upload()  # the task is never run: like a worker that is not running
        resume = Resume.objects.get()
        Resume.objects.filter(pk=resume.pk).update(updated_at=timezone.now() - timedelta(minutes=20))
        response = self.detail(resume)
        self.assertContains(response, "taking longer than usual")
        self.assertNotContains(response, 'http-equiv="refresh"')