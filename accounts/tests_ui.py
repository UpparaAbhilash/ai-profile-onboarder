"""UI and accessibility regression tests."""
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from profiles.tests_status import PASSWORD, User

PUBLIC_PAGES = ["/", "/resumes/upload/", "/jobs/", "/accounts/login/", "/accounts/privacy/"]


class LayoutTests(TestCase):
    def test_skip_link_points_to_main_content(self):
        response = self.client.get("/")
        self.assertContains(response, 'href="#main"')
        self.assertContains(response, 'id="main"')

    def test_static_files_exist(self):
        for path in ("img/favicon.svg", "js/ui.js", "js/confirm.js", "css/style.css"):
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path), f"static/{path} is missing")

    def test_current_page_is_marked_in_navigation(self):
        response = self.client.get(reverse("jobs:list"))
        self.assertContains(response, 'aria-current="page"', count=1)

    def test_home_page_call_to_action_depends_on_login(self):
        self.assertContains(self.client.get("/"), "Upload your resume")
        self.client.force_login(User.objects.create_user(email="asha@example.com", password=PASSWORD))
        self.assertContains(self.client.get("/"), "Go to my profile")

    def test_every_image_has_alt_text_and_every_page_has_one_h1(self):
        for url in PUBLIC_PAGES:
            with self.subTest(url=url):
                content = self.client.get(url).content.decode()
                for tag in re.findall(r"<img\b[^>]*>", content):
                    self.assertIn("alt=", tag)
                self.assertEqual(len(re.findall(r"<h1\b", content)), 1)


class UploadPageTests(TestCase):
    def test_upload_page_has_file_hints_and_loading_button(self):
        response = self.client.get(reverse("resumes:upload"))
        self.assertContains(response, f'data-max-mb="{settings.RESUME_MAX_UPLOAD_MB}"')
        self.assertContains(response, 'aria-describedby="file-help file-info"')
        self.assertContains(response, 'aria-live="polite"')
        self.assertContains(response, 'data-loading-text="Uploading…"')