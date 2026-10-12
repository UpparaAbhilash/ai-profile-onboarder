"""Automated tests for the custom User model and its manager."""
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class UserManagerTests(TestCase):
    def test_create_user_with_email_normalises_case(self):
        user = User.objects.create_user(email="Asha@Example.COM", password="S3cure-pass-123")
        self.assertEqual(user.email, "asha@example.com")
        self.assertTrue(user.check_password("S3cure-pass-123"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_password_is_hashed_not_stored_in_plaintext(self):
        user = User.objects.create_user(email="ravi@example.com", password="S3cure-pass-123")
        self.assertNotEqual(user.password, "S3cure-pass-123")
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))

    def test_user_without_password_gets_unusable_password(self):
        user = User.objects.create_user(email="new@example.com")
        self.assertFalse(user.has_usable_password())

    def test_email_is_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="S3cure-pass-123")

    def test_create_superuser(self):
        admin = User.objects.create_superuser(email="admin@example.com", password="S3cure-pass-123")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)


class HomePageTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI-Powered Profile Onboarder")