"""Tests for rare error paths: OpenAI failures, broken PDFs, database errors.
No real OpenAI call is ever made."""
import os
import shutil
import tempfile
from unittest.mock import patch

import httpx
import openai
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase, override_settings

from .models import Resume
from .services.ai_parser import ResumeParsingError, get_client, parse_resume_text
from .services.pdf_extraction import ExtractionError
from .services.pdf_validation import validate_resume_file
from .services.resume_intake import create_resume
from .tests import make_text_pdf, upload
from .tests_ai import REQUEST, SAMPLE_RESUME, fake_client, make_resume_data

TEMP_MEDIA_ROOT = tempfile.mkdtemp()


def status_error(error_class, status_code, message="error"):
    """Build an OpenAI HTTP error the way the SDK does, without any network call."""
    return error_class(message, response=httpx.Response(status_code, request=REQUEST), body=None)


@override_settings(OPENAI_API_KEY="test-key", OPENAI_MODEL="test-model")
class AIErrorMappingTests(SimpleTestCase):
    def test_each_openai_error_becomes_a_clear_message(self):
        # (error raised by the SDK, expected text in our message, retryable?)
        cases = [
            (openai.APIConnectionError(request=REQUEST), "Could not reach the AI service", True),
            (status_error(openai.RateLimitError, 429, "insufficient_quota"), "no remaining credit", False),
            (status_error(openai.BadRequestError, 400), "rejected the request", False),
            (status_error(openai.InternalServerError, 500), "HTTP 500", True),
            (status_error(openai.PermissionDeniedError, 403), "HTTP 403", False),
            (openai.OpenAIError("garbage"), "invalid response", False),
        ]
        for error, expected_text, retryable in cases:
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(ResumeParsingError) as cm:
                    parse_resume_text(SAMPLE_RESUME, client=fake_client(error=error))
                self.assertIn(expected_text, str(cm.exception))
                self.assertEqual(cm.exception.retryable, retryable)

    @override_settings(OPENAI_MODEL="")
    def test_missing_model_gives_clear_error(self):
        with self.assertRaisesMessage(ResumeParsingError, "OPENAI_MODEL is missing"):
            parse_resume_text(SAMPLE_RESUME, client=fake_client(make_resume_data()))

    @override_settings(RESUME_MAX_AI_INPUT_CHARS=50)
    def test_long_resume_is_shortened_before_sending(self):
        client = fake_client(make_resume_data())
        result = parse_resume_text(SAMPLE_RESUME, client=client)
        self.assertIn("Resume text was shortened before AI analysis.", result.warnings)
        sent_text = client.responses.parse.call_args.kwargs["input"][1]["content"]
        self.assertLess(len(sent_text), len(SAMPLE_RESUME))  # cost limit really applied

    @override_settings(OPENAI_API_KEY="sk-test-not-real", OPENAI_TIMEOUT_SECONDS=7)
    def test_client_uses_timeout_and_retry_settings(self):
        client = get_client()  # creating the client makes no network call
        self.assertEqual(client.timeout, 7)
        self.assertEqual(client.max_retries, 2)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class ResumeIntakeErrorTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def validated(self):
        return validate_resume_file(upload(make_text_pdf()))

    @patch("resumes.services.resume_intake.extract_text", side_effect=ExtractionError("broken"))
    def test_unreadable_pdf_is_saved_as_failed(self, mock_extract):
        resume = create_resume(self.validated(), "resume.pdf")
        self.assertEqual(resume.status, Resume.Status.FAILED)
        self.assertIn("could not read the text", resume.error_message)

    def count_files(self):
        return sum(len(names) for _, _, names in os.walk(TEMP_MEDIA_ROOT))

    def test_database_error_leaves_no_orphan_file(self):
        validated = self.validated()
        files_before = self.count_files()
        with patch.object(Resume, "save", side_effect=DatabaseError("database is down")):
            with self.assertRaises(DatabaseError):
                create_resume(validated, "resume.pdf")
        self.assertEqual(self.count_files(), files_before)  # the PDF on disk was deleted again