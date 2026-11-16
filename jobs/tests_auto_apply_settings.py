"""Tests for auto-apply settings and consent (Phase 17A). Nothing is applied in this phase."""
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from dashboard.models import AuditLog
from profiles.models import JobSeekerProfile
from profiles.tests_status import PASSWORD, User, make_complete_profile

from .forms import AutoApplyForm
from .models import Application, AutoApplyRule
from .services.auto_apply import AutoApplyError, save_rule

AUTO_APPLY_URL = reverse("jobs:auto_apply")
VALUES = {"min_match_percent": 80, "locations": ["Berlin"], "employment_types": [], "max_per_week": 3}


def form_data(**overrides):
    """POST data for the settings form. A value of None removes the field (unticked checkbox)."""
    data = {
        "enabled": "on",
        "consent": "on",
        "min_match_percent": "80",
        "locations": "Berlin, Remote",
        "employment_types": ["part_time"],
        "max_per_week": "3",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


class AutoApplyRuleModelTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()

    def test_defaults_are_safe(self):
        rule = AutoApplyRule.objects.create(profile=self.profile)
        self.assertFalse(rule.enabled)
        self.assertIsNone(rule.enabled_at)
        self.assertEqual((rule.min_match_percent, rule.max_per_week), (80, 3))

    def test_database_rejects_too_low_match(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AutoApplyRule.objects.create(profile=self.profile, min_match_percent=40)

    def test_database_rejects_too_many_per_week(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AutoApplyRule.objects.create(profile=self.profile, max_per_week=6)

    def test_database_rejects_on_without_consent_time(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AutoApplyRule.objects.create(profile=self.profile, enabled=True)


class AutoApplyFormTests(TestCase):
    def test_turning_on_needs_consent(self):
        form = AutoApplyForm(form_data(consent=None))
        self.assertFalse(form.is_valid())
        self.assertIn("consent", form.errors)

    def test_turning_off_needs_no_consent(self):
        self.assertTrue(AutoApplyForm(form_data(enabled=None, consent=None)).is_valid())

    def test_locations_are_cleaned(self):
        form = AutoApplyForm(form_data(locations=" Berlin ,remote,, berlin "))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["locations"], ["Berlin", "remote"])

    def test_too_many_locations(self):
        form = AutoApplyForm(form_data(locations=",".join(f"City{n}" for n in range(11))))
        self.assertIn("locations", form.errors)

    def test_limits_are_checked(self):
        for field, value in (("min_match_percent", "40"), ("max_per_week", "6"), ("max_per_week", "0")):
            with self.subTest(field=field, value=value):
                self.assertIn(field, AutoApplyForm(form_data(**{field: value})).errors)


class SaveRuleServiceTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()

    def actions(self):
        return list(AuditLog.objects.filter(action__startswith="auto_apply.").values_list("action", flat=True))

    def test_turning_on_stores_consent_time_and_is_audited(self):
        rule = save_rule(self.profile, self.user, enabled=True, **VALUES)
        self.assertTrue(rule.enabled)
        self.assertIsNotNone(rule.enabled_at)
        self.assertEqual(self.actions(), ["auto_apply.enabled"])

    def test_turning_off_clears_consent_time_and_is_audited(self):
        save_rule(self.profile, self.user, enabled=True, **VALUES)
        rule = save_rule(self.profile, self.user, enabled=False, **VALUES)
        self.assertIsNone(rule.enabled_at)
        self.assertIn("auto_apply.disabled", self.actions())

    def test_changing_rules_while_on_is_audited(self):
        save_rule(self.profile, self.user, enabled=True, **VALUES)
        save_rule(self.profile, self.user, enabled=True, **{**VALUES, "max_per_week": 5})
        self.assertIn("auto_apply.updated", self.actions())

    def test_saving_while_off_is_not_audited(self):
        save_rule(self.profile, self.user, enabled=False, **VALUES)
        self.assertEqual(self.actions(), [])

    def test_not_interested_cannot_turn_on(self):
        self.profile.status = JobSeekerProfile.Status.NOT_INTERESTED
        self.profile.save()
        with self.assertRaisesMessage(AutoApplyError, "Not Interested"):
            save_rule(self.profile, self.user, enabled=True, **VALUES)
        self.assertFalse(AutoApplyRule.objects.exists())

    def test_incomplete_profile_cannot_turn_on(self):
        self.profile.preferred_locations = []
        self.profile.save()
        with self.assertRaisesMessage(AutoApplyError, "complete your profile"):
            save_rule(self.profile, self.user, enabled=True, **VALUES)

    def test_turning_off_is_always_allowed(self):
        save_rule(self.profile, self.user, enabled=True, **VALUES)
        self.profile.preferred_locations = []
        self.profile.save()
        rule = save_rule(self.profile, self.user, enabled=False, **VALUES)
        self.assertFalse(rule.enabled)


class AutoApplyViewTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()

    def test_login_is_required(self):
        response = self.client.get(AUTO_APPLY_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_user_without_profile_is_sent_to_upload(self):
        self.client.force_login(User.objects.create_user(email="new@example.com", password=PASSWORD))
        self.assertRedirects(self.client.get(AUTO_APPLY_URL), reverse("resumes:upload"))

    def test_opening_the_page_creates_nothing(self):
        self.client.force_login(self.user)
        response = self.client.get(AUTO_APPLY_URL)
        self.assertContains(response, "Off")
        self.assertFalse(AutoApplyRule.objects.exists())

    def test_turning_on(self):
        self.client.force_login(self.user)
        response = self.client.post(AUTO_APPLY_URL, form_data(), follow=True)
        self.assertRedirects(response, AUTO_APPLY_URL)
        self.assertContains(response, "Auto-apply is on")
        rule = AutoApplyRule.objects.get(profile=self.profile)
        self.assertTrue(rule.enabled)
        self.assertEqual(rule.locations, ["Berlin", "Remote"])
        self.assertEqual(rule.employment_types, ["part_time"])

    def test_without_consent_nothing_is_saved(self):
        self.client.force_login(self.user)
        response = self.client.post(AUTO_APPLY_URL, form_data(consent=None))
        self.assertContains(response, "Please confirm that we may apply for you.")
        self.assertFalse(AutoApplyRule.objects.exists())

    def test_service_error_is_shown_above_the_form(self):
        self.profile.status = JobSeekerProfile.Status.NOT_INTERESTED
        self.profile.save()
        self.client.force_login(self.user)
        response = self.client.post(AUTO_APPLY_URL, form_data())
        self.assertContains(response, "Open to Work")
        self.assertFalse(AutoApplyRule.objects.exists())

    def test_settings_never_apply(self):
        self.client.force_login(self.user)
        self.client.post(AUTO_APPLY_URL, form_data())
        self.assertEqual(Application.objects.count(), 0)

    def test_recommended_page_links_to_settings(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("jobs:recommended")), AUTO_APPLY_URL)