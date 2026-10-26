"""Tests for the profile status workflow."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from dashboard.models import AuditLog

from .models import JobSeekerProfile, Skill
from .services.completeness import missing_required_fields
from .services.status import StatusChangeError, change_status

User = get_user_model()
Status = JobSeekerProfile.Status
PASSWORD = "S3cure-pass-123"


def make_complete_profile(email="asha@example.com"):
    user = User.objects.create_user(email=email, password=PASSWORD)
    profile = JobSeekerProfile.objects.create(
        user=user,
        first_name="Asha",
        last_name="Rao",
        phone="+491761234567",
        current_city="Berlin",
        professional_role="Python Developer",
        experience_type="experienced",
        total_experience_months=30,
        preferred_locations=["Berlin"],
    )
    for name in ("Python", "Django", "MySQL"):
        profile.skills.add(Skill.objects.get_or_create(name=name)[0])
    return user, profile


class StatusServiceTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()
        self.reviewer = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)

    def test_candidate_can_become_open_to_work_when_complete(self):
        entry = change_status(self.profile, Status.OPEN_TO_WORK, self.user)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, Status.OPEN_TO_WORK)
        self.assertEqual(entry.from_status, Status.CREATED)
        self.assertEqual(entry.changed_by, self.user)
        audit = AuditLog.objects.get(action="profile.status_changed")
        self.assertEqual(audit.target, self.profile)
        self.assertEqual(audit.details["to"], Status.OPEN_TO_WORK)

    def test_open_to_work_requires_complete_profile(self):
        self.profile.phone = ""
        self.profile.save()
        with self.assertRaisesMessage(StatusChangeError, "Phone"):
            change_status(self.profile, Status.OPEN_TO_WORK, self.user)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, Status.CREATED)
        self.assertEqual(self.profile.status_history.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_candidate_can_switch_between_open_and_not_interested(self):
        change_status(self.profile, Status.NOT_INTERESTED, self.user)
        change_status(self.profile, Status.OPEN_TO_WORK, self.user)
        change_status(self.profile, Status.NOT_INTERESTED, self.user)
        self.assertEqual(self.profile.status_history.count(), 3)

    def test_candidate_cannot_mark_own_profile_reviewed(self):
        regular = User.objects.get(pk=self.user.pk)
        with self.assertRaisesMessage(StatusChangeError, "permission to review"):
            change_status(self.profile, Status.REVIEWED, regular)

    def test_reviewer_can_mark_created_profile_reviewed(self):
        change_status(self.profile, Status.REVIEWED, self.reviewer)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, Status.REVIEWED)

    def test_user_with_only_the_review_permission_can_review(self):
        staff = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="review_profile"))
        staff = User.objects.get(pk=staff.pk)  # reload: permissions are cached per object
        change_status(self.profile, Status.REVIEWED, staff)
        self.assertEqual(self.profile.status, Status.REVIEWED)

    def test_staff_without_permission_cannot_review(self):
        staff = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
        with self.assertRaisesMessage(StatusChangeError, "permission to review"):
            change_status(self.profile, Status.REVIEWED, staff)

    def test_reviewer_cannot_choose_open_to_work_for_the_candidate(self):
        with self.assertRaisesMessage(StatusChangeError, "Only the candidate"):
            change_status(self.profile, Status.OPEN_TO_WORK, self.reviewer)

    def test_reviewer_cannot_overwrite_the_candidates_choice(self):
        change_status(self.profile, Status.OPEN_TO_WORK, self.user)
        with self.assertRaisesMessage(StatusChangeError, "cannot change"):
            change_status(self.profile, Status.REVIEWED, self.reviewer)

    def test_unknown_status_is_rejected(self):
        with self.assertRaisesMessage(StatusChangeError, "Unknown status"):
            change_status(self.profile, "hired", self.user)

    def test_missing_fields_lists_experience_and_skills(self):
        self.profile.total_experience_months = None
        self.profile.save()
        self.profile.skills.remove(Skill.objects.get(name="MySQL"))
        missing = missing_required_fields(self.profile)
        self.assertIn("Total experience", missing)
        self.assertIn("At least 3 skills", missing)


class StatusViewTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_complete_profile()

    def test_candidate_changes_status_on_profile_page(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("profiles:change_status"), {"status": Status.OPEN_TO_WORK})
        self.assertRedirects(response, reverse("profiles:me"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, Status.OPEN_TO_WORK)

    def test_incomplete_profile_shows_clear_error(self):
        self.profile.current_city = ""
        self.profile.save()
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profiles:change_status"), {"status": Status.OPEN_TO_WORK}, follow=True
        )
        self.assertContains(response, "Please complete your profile first")
        self.assertContains(response, "Current city")

    def test_status_change_requires_login_and_post(self):
        url = reverse("profiles:change_status")
        self.assertRedirects(self.client.post(url, {"status": "open_to_work"}),
                             f"{reverse('accounts:login')}?next={url}")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_admin_action_marks_profiles_reviewed(self):
        admin_user = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        self.client.force_login(admin_user)
        self.client.post(
            reverse("admin:profiles_jobseekerprofile_changelist"),
            {"action": "mark_reviewed", "_selected_action": [str(self.profile.pk)]},
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, Status.REVIEWED)

    def test_status_is_read_only_in_admin(self):
        admin_user = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        self.client.force_login(admin_user)
        response = self.client.get(
            reverse("admin:profiles_jobseekerprofile_change", args=[self.profile.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="status"')