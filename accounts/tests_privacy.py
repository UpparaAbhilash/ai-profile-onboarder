"""Tests for the right to erasure and the data retention cleanup."""
import os
import shutil
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from dashboard.models import AuditLog
from jobs.models import Application
from jobs.services.applications import apply_to_job
from jobs.test_applications import make_job
from profiles.models import JobSeekerProfile
from profiles.tests_status import PASSWORD, User, make_complete_profile
from resumes.models import Resume
from resumes.services.pdf_validation import validate_resume_file
from resumes.services.resume_intake import create_resume
from resumes.tests import make_text_pdf, upload

from .services.privacy import delete_account

TEMP_MEDIA_ROOT = tempfile.mkdtemp()


def make_resume(owner=None):
    return create_resume(validate_resume_file(upload(make_text_pdf())), "resume.pdf", owner=owner)


def file_exists(resume):
    return resume.file.storage.exists(resume.file.name)


def make_old(queryset, days, field="created_at"):
    """Pretend rows were created `days` ago (update() skips auto_now_add)."""
    queryset.update(**{field: timezone.now() - timedelta(days=days)})


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class DeleteAccountTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user, self.profile = make_complete_profile("asha@example.com")
        self.resume = make_resume(owner=self.user)
        apply_to_job(self.profile, make_job())

    def test_everything_is_deleted_including_the_pdf_file(self):
        self.assertTrue(file_exists(self.resume))
        with self.captureOnCommitCallbacks(execute=True):  # files are removed after commit
            delete_account(self.user, reason="user_request")

        self.assertFalse(User.objects.filter(email="asha@example.com").exists())
        self.assertFalse(JobSeekerProfile.objects.exists())
        self.assertFalse(Resume.objects.exists())
        self.assertFalse(Application.objects.exists())
        self.assertFalse(file_exists(self.resume))

    def test_deletion_is_audited_without_personal_data(self):
        with self.captureOnCommitCallbacks(execute=True):
            delete_account(self.user, reason="user_request")
        entry = AuditLog.objects.get(action="account.deleted")
        self.assertEqual(entry.details, {"reason": "user_request", "resumes": 1, "applications": 1})
        self.assertNotIn("asha", str(entry.details))

    def test_unlinked_resume_with_the_same_email_is_deleted_too(self):
        unlinked = make_resume()
        unlinked.status = Resume.Status.PARSED
        unlinked.parsed_data = {"fields": {"email": "asha@example.com"}}
        unlinked.save()
        with self.captureOnCommitCallbacks(execute=True):
            counts = delete_account(self.user, reason="user_request")
        self.assertEqual(counts["resumes"], 2)
        self.assertFalse(Resume.objects.filter(pk=unlinked.pk).exists())
        self.assertFalse(file_exists(unlinked))


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT, UNCLAIMED_DATA_RETENTION_DAYS=30, AUDIT_LOG_RETENTION_DAYS=365)
class PurgeOldDataTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def purge(self, *args):
        out = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("purge_old_data", *args, stdout=out)
        return out.getvalue()

    def test_old_unclaimed_resume_is_deleted_new_one_is_kept(self):
        old, new = make_resume(), make_resume()
        make_old(Resume.objects.filter(pk=old.pk), days=31)
        output = self.purge()
        self.assertIn("Deleted 1 unclaimed resumes", output)
        self.assertFalse(Resume.objects.filter(pk=old.pk).exists())
        self.assertFalse(file_exists(old))
        self.assertTrue(Resume.objects.filter(pk=new.pk).exists())

    def test_dry_run_deletes_nothing(self):
        old = make_resume()
        make_old(Resume.objects.filter(pk=old.pk), days=31)
        output = self.purge("--dry-run")
        self.assertIn("Would delete 1 unclaimed resumes", output)
        self.assertTrue(Resume.objects.filter(pk=old.pk).exists())
        self.assertTrue(file_exists(old))

    def test_only_never_used_auto_created_accounts_are_deleted(self):
        never_used = User.objects.create_user(email="onboarded@example.com")  # unusable password
        reviewer = User.objects.create_user(email="reviewer@example.com", password=PASSWORD)
        returning = User.objects.create_user(email="returning@example.com")
        returning.last_login = timezone.now()
        returning.save()
        make_old(User.objects.all(), days=31, field="date_joined")

        self.purge()

        self.assertFalse(User.objects.filter(pk=never_used.pk).exists())
        self.assertTrue(User.objects.filter(pk=reviewer.pk).exists())   # has a real password
        self.assertTrue(User.objects.filter(pk=returning.pk).exists())  # has logged in

    def test_old_audit_entries_are_deleted(self):
        old = AuditLog.objects.create(action="test.old")
        recent = AuditLog.objects.create(action="test.recent")
        make_old(AuditLog.objects.filter(pk=old.pk), days=366)
        self.purge()
        self.assertFalse(AuditLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(AuditLog.objects.filter(pk=recent.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action="data.purged").exists())

    def test_orphan_files_are_deleted_but_known_files_are_kept(self):
        known = make_resume()
        orphan = Path(TEMP_MEDIA_ROOT) / "resumes" / "2020" / "01" / "orphan.pdf"
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_bytes(b"%PDF-1.4 leftover")
        two_hours_ago = timezone.now().timestamp() - 2 * 60 * 60
        for path in (orphan, Path(known.file.path)):
            os.utime(path, (two_hours_ago, two_hours_ago))

        output = self.purge()

        self.assertIn("Deleted 1 orphan files", output)
        self.assertFalse(orphan.exists())
        self.assertTrue(file_exists(known))