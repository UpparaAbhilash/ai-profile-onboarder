"""Celery configuration tests. Run without Redis thanks to eager mode."""
from django.conf import settings
from django.test import SimpleTestCase

from config.celery import app, ping


class CeleryConfigTests(SimpleTestCase):
    def test_tests_run_tasks_eagerly(self):
        self.assertTrue(settings.CELERY_TASK_ALWAYS_EAGER)
        self.assertTrue(app.conf.task_always_eager)

    def test_ping_task_returns_pong(self):
        self.assertEqual(ping.delay().get(timeout=5), "pong")

    def test_only_json_messages_are_accepted(self):
        self.assertEqual(list(app.conf.accept_content), ["json"])