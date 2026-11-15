"""Tests for AI cover note drafts (Phase 16B). OpenAI is never called: a fake client is used."""
from types import SimpleNamespace
from unittest.mock import patch

import openai
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from profiles.tests_status import make_complete_profile
from resumes.tests_ai import REQUEST, fake_client

from .models import Application
from .services.cover_note import (
    DRAFT_FAILED_MESSAGE,
    MAX_JOB_TEXT_CHARS,
    MAX_NOTE_CHARS,
    CoverNoteDraft,
    CoverNoteError,
    generate_cover_note,
    take_draft_slot,
)
from .test_applications import make_job

User = get_user_model()
DRAFT = "Dear hiring team,\n\nI work with Python and Django every day.\n\nKind regards"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "cover-tests"}}


def sent_text(client) -> str:
    """Everything the fake AI received, as one string."""
    messages = client.responses.parse.call_args.kwargs["input"]
    return "\n".join(message["content"] for message in messages)


@override_settings(OPENAI_MODEL="test-model")
class GenerateCoverNoteTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()  # Asha Rao, Python/Django/MySQL
        self.job = make_job(title="Django Developer", company="Example GmbH")

    def test_returns_the_draft(self):
        client = fake_client(CoverNoteDraft(cover_note=DRAFT))
        self.assertEqual(generate_cover_note(self.profile, self.job, client=client), DRAFT)
        self.assertEqual(client.responses.parse.call_args.kwargs["model"], "test-model")

    def test_ai_gets_skills_and_job_but_no_personal_data(self):
        client = fake_client(CoverNoteDraft(cover_note=DRAFT))
        generate_cover_note(self.profile, self.job, client=client)
        text = sent_text(client)
        for expected in ("Python", "Django Developer", "Example GmbH", "2.5 years"):
            self.assertIn(expected, text)
        for personal in ("Asha", "Rao", "asha@example.com", "1761234567"):
            self.assertNotIn(personal, text)

    def test_long_job_description_is_shortened(self):
        self.job.description = "x" * (MAX_JOB_TEXT_CHARS + 500)
        self.job.save()
        client = fake_client(CoverNoteDraft(cover_note=DRAFT))
        generate_cover_note(self.profile, self.job, client=client)
        self.assertIn("x" * MAX_JOB_TEXT_CHARS, sent_text(client))
        self.assertNotIn("x" * (MAX_JOB_TEXT_CHARS + 1), sent_text(client))

    def test_draft_is_cleaned_and_limited(self):
        messy = "  Dear hiring team,\n\n\n\n" + "a" * 3000
        client = fake_client(CoverNoteDraft(cover_note=messy))
        note = generate_cover_note(self.profile, self.job, client=client)
        self.assertTrue(note.startswith("Dear hiring team,\n\na"))
        self.assertLessEqual(len(note), MAX_NOTE_CHARS)

    def test_ai_error_gives_friendly_message(self):
        client = fake_client(error=openai.APITimeoutError(request=REQUEST))
        with self.assertLogs("jobs.services.cover_note", level="WARNING"):
            with self.assertRaisesMessage(CoverNoteError, DRAFT_FAILED_MESSAGE):
                generate_cover_note(self.profile, self.job, client=client)

    def test_empty_answer_is_an_error(self):
        for parsed in (None, CoverNoteDraft(cover_note="   ")):
            with self.subTest(parsed=parsed):
                with self.assertRaises(CoverNoteError):
                    generate_cover_note(self.profile, self.job, client=fake_client(parsed))

    def test_missing_api_key_gives_friendly_message(self):
        # Tests always run without an API key, so the real client cannot be created.
        with self.assertLogs("jobs.services.cover_note", level="WARNING"):
            with self.assertRaisesMessage(CoverNoteError, "not available"):
                generate_cover_note(self.profile, self.job)

    @override_settings(OPENAI_MODEL="")
    def test_missing_model_gives_friendly_message(self):
        with self.assertRaisesMessage(CoverNoteError, "not available"):
            generate_cover_note(self.profile, self.job, client=fake_client())


@override_settings(CACHES=LOCMEM, COVER_NOTE_DAILY_LIMIT=2)
class DailyLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user, _ = make_complete_profile()

    def test_limit_per_user_per_day(self):
        self.assertTrue(take_draft_slot(self.user))
        self.assertTrue(take_draft_slot(self.user))
        self.assertFalse(take_draft_slot(self.user))

    def test_other_users_have_their_own_limit(self):
        other, _ = make_complete_profile(email="other@example.com")
        take_draft_slot(self.user)
        take_draft_slot(self.user)
        self.assertTrue(take_draft_slot(other))


class DraftCoverNoteViewTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()
        self.job = make_job()
        self.draft_url = reverse("jobs:draft_cover_note", args=[self.job.pk])
        self.detail_url = reverse("jobs:detail", args=[self.job.pk])

    def login_and_draft(self, **kwargs):
        self.client.force_login(self.user)
        return self.client.post(self.draft_url, **kwargs)

    @patch("jobs.views.generate_cover_note", return_value=DRAFT)
    def test_draft_is_shown_in_the_cover_note_box(self, mock_generate):
        response = self.login_and_draft(follow=True)
        self.assertRedirects(response, self.detail_url)
        self.assertContains(response, "I work with Python and Django every day.")
        self.assertContains(response, "AI draft.")
        mock_generate.assert_called_once()

    @patch("jobs.views.generate_cover_note", return_value=DRAFT)
    def test_drafting_never_applies(self, mock_generate):
        self.login_and_draft(follow=True)
        self.assertEqual(Application.objects.count(), 0)

    @patch("jobs.views.generate_cover_note", return_value=DRAFT)
    def test_draft_is_shown_only_once(self, mock_generate):
        self.login_and_draft(follow=True)
        response = self.client.get(self.detail_url)  # e.g. the user reloads the page
        self.assertNotContains(response, "AI draft.")
        mock_generate.assert_called_once()  # reloading does not call the AI again

    @patch("jobs.views.generate_cover_note")
    def test_incomplete_profile_cannot_draft(self, mock_generate):
        self.profile.preferred_locations = []
        self.profile.save()
        response = self.login_and_draft(follow=True)
        self.assertContains(response, "only draft a cover note for a job you can apply for")
        mock_generate.assert_not_called()

    @patch("jobs.views.generate_cover_note")
    def test_cannot_draft_after_applying(self, mock_generate):
        Application.objects.create(job=self.job, candidate=self.profile)
        self.login_and_draft()
        mock_generate.assert_not_called()

    @override_settings(COVER_NOTE_DAILY_LIMIT=0)
    @patch("jobs.views.generate_cover_note")
    def test_daily_limit_stops_the_ai_call(self, mock_generate):
        response = self.login_and_draft(follow=True)
        self.assertContains(response, "today&#x27;s limit of 0 AI drafts")
        mock_generate.assert_not_called()

    @patch("jobs.views.generate_cover_note", side_effect=CoverNoteError(DRAFT_FAILED_MESSAGE))
    def test_ai_error_is_shown_to_the_user(self, mock_generate):
        response = self.login_and_draft(follow=True)
        self.assertContains(response, "could not write a draft right now")
        self.assertNotContains(response, "AI draft.")

    def test_login_is_required(self):
        response = self.client.post(self.draft_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_get_is_not_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.draft_url).status_code, 405)

    def test_closed_job_gives_404(self):
        self.job.is_active = False
        self.job.save()
        self.assertEqual(self.login_and_draft().status_code, 404)

    def test_button_is_shown_only_when_the_candidate_can_apply(self):
        self.assertNotContains(self.client.get(self.detail_url), self.draft_url)  # anonymous
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.detail_url), self.draft_url)
