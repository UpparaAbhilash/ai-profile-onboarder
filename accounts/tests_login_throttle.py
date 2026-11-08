"""Tests for login rate limiting (brute-force protection)."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .services.login_throttle import MAX_FAILURES_PER_EMAIL, MAX_FAILURES_PER_IP, throttle_key

User = get_user_model()
LOGIN_URL = reverse("accounts:login")
EMAIL = "asha@example.com"
PASSWORD = "S3cure-pass-123"
WRONG = "wrong-password-123"
LOCKED_TEXT = "Too many failed login attempts"
# The rest of the test suite uses a dummy cache; these tests need a real one.
THROTTLE_CACHE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "throttle-tests"}
}


@override_settings(CACHES=THROTTLE_CACHE)
class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email=EMAIL, password=PASSWORD)

    def login(self, email=EMAIL, password=WRONG):
        return self.client.post(LOGIN_URL, {"username": email, "password": password})

    def fail(self, times, email=EMAIL):
        for _ in range(times):
            self.login(email=email)

    def test_correct_password_is_refused_during_lockout(self):
        self.fail(MAX_FAILURES_PER_EMAIL)
        response = self.login(password=PASSWORD)
        self.assertContains(response, LOCKED_TEXT, status_code=429)
        self.assertNotIn("_auth_user_id", self.client.session)  # not logged in

    def test_fewer_failures_do_not_lock(self):
        self.fail(MAX_FAILURES_PER_EMAIL - 1)
        self.assertEqual(self.login(password=PASSWORD).status_code, 302)

    def test_successful_login_resets_the_counter(self):
        self.fail(MAX_FAILURES_PER_EMAIL - 1)
        self.login(password=PASSWORD)
        self.client.logout()
        self.fail(MAX_FAILURES_PER_EMAIL - 1)
        self.assertEqual(self.login(password=PASSWORD).status_code, 302)

    def test_lock_applies_only_to_that_email(self):
        User.objects.create_user(email="ravi@example.com", password=PASSWORD)
        self.fail(MAX_FAILURES_PER_EMAIL)
        self.assertEqual(self.login(email="ravi@example.com", password=PASSWORD).status_code, 302)

    def test_unknown_email_is_locked_the_same_way(self):
        # Same behaviour with and without an account: attackers learn nothing.
        self.fail(MAX_FAILURES_PER_EMAIL, email="nobody@example.com")
        self.assertContains(self.login(email="nobody@example.com"), LOCKED_TEXT, status_code=429)

    def test_one_ip_trying_many_accounts_is_blocked(self):
        for number in range(MAX_FAILURES_PER_IP):
            self.login(email=f"user{number}@example.com")
        self.assertContains(self.login(password=PASSWORD), LOCKED_TEXT, status_code=429)

    def test_admin_login_is_protected_too(self):
        self.user.is_staff = True
        self.user.save()
        self.fail(MAX_FAILURES_PER_EMAIL)
        response = self.client.post(
            "/admin/login/", {"username": EMAIL, "password": PASSWORD, "next": "/admin/"}
        )
        self.assertEqual(response.status_code, 200)  # form shown again, no redirect
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cache_keys_contain_no_email_address(self):
        self.assertNotIn("asha", throttle_key("email", EMAIL))