"""Tests for storing AI results and the upload flow with AI. OpenAI is never called."""
import shutil
import tempfile
from io import StringIO
from unittest.mock import patch

import openai
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Resume
from .services.pdf_validation import validate_resume_file
from .services.resume_intake import create_resume
from .services.resume_parsing import parse_and_store
from .tests import make_image_only_pdf, make_text_pdf, upload
from .tests_ai import REQUEST, fake_client, make_resume_data

TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT, OPENAI_MODEL="test-model", OPENAI_API_KEY="")
class ResumeParsingFlowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def make_resume(self, pdf_bytes=None):
        validated = validate_resume_file(upload(pdf_bytes or make_text_pdf()))
        return create_resume(validated, "resume.pdf")

    def test_successful_parse_is_saved(self):
        resume = parse_and_store(self.make_resume(), client=fake_client(make_resume_data()))
        resume.refresh_from_db()
        self.assertEqual(resume.status, Resume.Status.PARSED)
        self.assertEqual(resume.ai_model, "test-model")
        self.assertIsNotNone(resume.parsed_at)
        fields = resume.parsed_data["fields"]
        self.assertEqual(fields["email"], "asha.rao@example.com")
        # "Acme Corp" is not in this test PDF's text, so verification removed it.
        self.assertIsNone(fields["current_company"])
        self.assertTrue(resume.parsed_data["warnings"])

    def test_ai_error_keeps_text_and_records_message(self):
        error = openai.APITimeoutError(request=REQUEST)
        resume = parse_and_store(self.make_resume(), client=fake_client(error=error))
        resume.refresh_from_db()
        self.assertEqual(resume.status, Resume.Status.EXTRACTED)  # can be retried later
        self.assertIn("timed out", resume.error_message)
        self.assertIsNone(resume.parsed_data)
        self.assertTrue(resume.extracted_text)

    def test_scanned_resume_is_never_sent_to_ai(self):
        client = fake_client(make_resume_data())
        resume = self.make_resume(make_image_only_pdf())
        parse_and_store(resume, client=client)
        client.responses.parse.assert_not_called()
        self.assertEqual(resume.status, Resume.Status.FAILED)

    @patch("resumes.services.ai_parser.get_client")
    def test_upload_runs_ai_and_shows_results(self, mock_get_client):
        mock_get_client.return_value = fake_client(make_resume_data())
        # execute=True runs the queued background task (eagerly, in this process).
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("resumes:upload"), {"file": upload(make_text_pdf())})
        resume = Resume.objects.get()
        self.assertEqual(resume.status, Resume.Status.PARSED)
        response = self.client.get(reverse("resumes:detail", args=[resume.pk]))
        self.assertContains(response, "asha.rao@example.com")
        self.assertContains(response, "Extracted details")

    def test_upload_without_ai_configuration_still_works(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("resumes:upload"), {"file": upload(make_text_pdf())})
        resume = Resume.objects.get()
        self.assertEqual(resume.status, Resume.Status.EXTRACTED)
        self.assertIn("not configured", resume.error_message)
        response = self.client.get(reverse("resumes:detail", args=[resume.pk]))
        self.assertEqual(response.status_code, 200)

    @patch("resumes.services.ai_parser.get_client")
    def test_reparse_command(self, mock_get_client):
        mock_get_client.return_value = fake_client(make_resume_data())
        resume = self.make_resume()
        out = StringIO()
        call_command("reparse_resume", str(resume.pk), stdout=out)
        resume.refresh_from_db()
        self.assertEqual(resume.status, Resume.Status.PARSED)
        self.assertIn(f"Resume {resume.pk}: Parsed", out.getvalue())