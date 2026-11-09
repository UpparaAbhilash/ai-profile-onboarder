"""Tests for deployment helpers: health check and the scheduled retention cleanup."""
import shutil
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase, override_settings

from .tasks import purge_old_data_task

TEMP_MEDIA_ROOT = tempfile.mkdtemp()


class HealthCheckTests(TestCase):
    def test_health_check_reports_ok(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @patch("config.views.connection")
    def test_health_check_reports_database_problems(self, mock_connection):
        mock_connection.cursor.side_effect = DatabaseError("database is down")
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error"})


class ScheduleTests(SimpleTestCase):
    def test_retention_cleanup_runs_every_day(self):
        entry = settings.CELERY_BEAT_SCHEDULE["purge-old-data-daily"]
        self.assertEqual(entry["task"], "accounts.purge_old_data")


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)  # never touch real files in tests
class PurgeTaskTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def test_purge_task_runs_the_cleanup(self):
        counts = purge_old_data_task()
        self.assertEqual(
            set(counts), {"inactive accounts", "unclaimed resumes", "audit log entries", "orphan files"}
        )