"""Security regression tests: headers, Content Security Policy, templates."""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

INLINE_HANDLER = re.compile(r"<[^>]*\son[a-z]+\s*=", re.IGNORECASE)  # e.g. onsubmit="..."
TEMPLATE_FOLDERS = ["templates", "accounts", "dashboard", "jobs", "profiles", "resumes"]


class SecurityHeaderTests(TestCase):
    def setUp(self):
        self.response = self.client.get("/")

    def test_security_headers_are_set(self):
        headers = self.response.headers
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "same-origin")
        self.assertEqual(headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertIn("camera=()", headers["Permissions-Policy"])

    def test_content_security_policy_blocks_inline_scripts(self):
        policy = self.response.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("object-src 'none'", policy)
        script_src = next(part for part in policy.split(";") if part.strip().startswith("script-src"))
        self.assertNotIn("unsafe-inline", script_src)
        self.assertNotIn("unsafe-eval", script_src)


class TemplateSafetyTests(TestCase):
    def test_no_inline_event_handlers_in_templates(self):
        """onclick=, onsubmit=, ... would be blocked by the CSP, so they must not exist."""
        offenders = []
        for folder in TEMPLATE_FOLDERS:
            for path in (Path(settings.BASE_DIR) / folder).rglob("*.html"):
                if INLINE_HANDLER.search(path.read_text(encoding="utf-8")):
                    offenders.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertEqual(offenders, [], f"Inline event handlers found in: {offenders}")