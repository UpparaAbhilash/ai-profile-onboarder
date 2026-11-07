"""Tests for the reparse_resume --queue option. No Redis, no OpenAI."""
import shutil
import tempfile
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from kombu.exceptions import OperationalError

from .models import Resume
from .services.pdf_validation import validate_resume_file
from .services.resume_intake import create_resume
from .tests import make_image_only_pdf, make_text_pdf, upload
from .tests_ai import fake_client, make_resume_data

TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT, OPENAI_MODEL="test-model", OPENAI_API_KEY="")
class ReparseQueueCommandTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def make_resume(self, pdf_bytes=None):
        validated = validate_resume_file(upload(pdf_bytes or make_text_pdf()))
        return create_resume(validated, "resume.pdf")

    def run_command(self, *args):
        out = StringIO()
        call_command("reparse_resume", *args, stdout=out)
        return out.getvalue()

    @patch("resumes.services.ai_parser.get_client")
    def test_queue_sends_stuck_resumes_to_the_worker(self, mock_get_client):
        mock_get_client.return_value = fake_client(make_resume_data())
        resume = self.make_resume()
        Resume.objects.filter(pk=resume.pk).update(error_message="AI analysis failed: timed out")

        output = self.run_command("--pending", "--queue")

        self.assertIn(f"Resume {resume.pk}: queued", output)
        resume.refresh_from_db()
        self.assertEqual(resume.status, Resume.Status.PARSED)  # eager mode: the task ran at once
        self.assertEqual(resume.error_message, "")

    def test_queue_skips_resumes_that_are_not_waiting(self):
        scanned = self.make_resume(make_image_only_pdf())  # status FAILED
        output = self.run_command(str(scanned.pk), "--queue")
        self.assertIn(f"Resume {scanned.pk}: skipped", output)
        self.assertIn("0 resume(s) sent", output)

    @patch("resumes.management.commands.reparse_resume.parse_resume_task")
    def test_clear_error_when_redis_is_down(self, mock_task):
        mock_task.delay.side_effect = OperationalError("Redis is down")
        resume = self.make_resume()
        with self.assertRaisesMessage(CommandError, "Redis is not reachable"):
            self.run_command(str(resume.pk), "--queue")