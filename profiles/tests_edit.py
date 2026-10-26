"""Tests for the Edit profile page: validation, formsets and ownership."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import JobSeekerProfile, Project, Skill

User = get_user_model()
PASSWORD = "S3cure-pass-123"
URL = reverse("profiles:edit")


def management(prefix, total=0, initial=0):
    return {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


def form_data(**overrides):
    data = {
        "first_name": "Asha",
        "last_name": "Rao",
        "surname": "",
        "phone": "+49 176 1234567",
        "date_of_birth": "1998-05-14",
        "aadhaar_last4": "",
        "current_city": "Berlin",
        "professional_role": "Python Developer",
        "current_company": "Acme",
        "experience_type": "experienced",
        "experience_years": "2",
        "experience_months": "6",
        "skills_text": "Python, Django",
        "preferred_roles_text": "Backend Developer",
        "preferred_locations_text": "Berlin, Munich",
        "experience_summary": "",
        **management("projects"),
        **management("achievements"),
    }
    data.update(overrides)
    return data


class EditProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="asha@example.com", password=PASSWORD)
        self.profile = JobSeekerProfile.objects.create(
            user=self.user, first_name="Asha", total_experience_months=30
        )
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(URL)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={URL}")

    def test_user_without_profile_is_sent_to_upload(self):
        other = User.objects.create_user(email="new@example.com", password=PASSWORD)
        self.client.force_login(other)
        self.assertRedirects(self.client.get(URL), reverse("resumes:upload"))

    def test_page_shows_current_values(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="experience_years" value="2"')
        self.assertContains(response, 'name="experience_months" value="6"')

    def test_valid_post_updates_profile_skills_and_experience(self):
        data = form_data(skills_text="Python, django, Django, MySQL", experience_years="3",
                         experience_months="1")
        self.assertRedirects(self.client.post(URL, data), reverse("profiles:me"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_experience_months, 37)
        self.assertEqual(self.profile.preferred_locations, ["Berlin", "Munich"])
        self.assertEqual(self.profile.date_of_birth, date(1998, 5, 14))
        names = {name.lower() for name in self.profile.skills.values_list("name", flat=True)}
        self.assertEqual(names, {"python", "django", "mysql"})

    def test_phone_is_normalised(self):
        self.client.post(URL, form_data(phone="+49 176-1234 567"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.phone, "+491761234567")

    def test_unrealistic_date_of_birth_is_rejected(self):
        response = self.client.post(URL, form_data(date_of_birth="2020-01-01"))
        self.assertContains(response, "realistic date of birth")
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.date_of_birth)

    def test_full_aadhaar_number_is_rejected_and_never_stored(self):
        response = self.client.post(URL, form_data(aadhaar_last4="2345 6789 0123"))
        self.assertContains(response, "Enter only the last 4 digits")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.aadhaar_last4, "")

    def test_last_four_aadhaar_digits_are_saved_masked(self):
        self.client.post(URL, form_data(aadhaar_last4="0123"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.aadhaar_masked, "XXXX-XXXX-0123")

    def test_project_ending_before_start_is_rejected_and_nothing_is_saved(self):
        data = form_data(
            first_name="Changed",
            **management("projects", total=1),
            **{
                "projects-0-title": "Broken dates",
                "projects-0-start_date": "2025-06-01",
                "projects-0-end_date": "2025-01-01",
            },
        )
        response = self.client.post(URL, data)
        self.assertContains(response, "End date cannot be before the start date")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.first_name, "Asha")  # all-or-nothing
        self.assertEqual(self.profile.projects.count(), 0)

    def test_new_project_can_be_added(self):
        data = form_data(
            **management("projects", total=1),
            **{"projects-0-title": "Resume Parser", "projects-0-start_date": "2024-01-01"},
        )
        self.assertRedirects(self.client.post(URL, data), reverse("profiles:me"))
        self.assertEqual(self.profile.projects.get().title, "Resume Parser")

    def test_project_can_be_deleted(self):
        project = Project.objects.create(profile=self.profile, title="Old project")
        data = form_data(
            **management("projects", total=1, initial=1),
            **{
                "projects-0-id": str(project.pk),
                "projects-0-title": "Old project",
                "projects-0-DELETE": "on",
            },
        )
        self.assertRedirects(self.client.post(URL, data), reverse("profiles:me"))
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_cannot_change_another_users_project_with_a_forged_id(self):
        other_user = User.objects.create_user(email="ravi@example.com", password=PASSWORD)
        other_profile = JobSeekerProfile.objects.create(user=other_user)
        victim = Project.objects.create(profile=other_profile, title="Ravi's project")
        data = form_data(
            **management("projects", total=1, initial=1),
            **{"projects-0-id": str(victim.pk), "projects-0-title": "Hacked"},
        )
        self.client.post(URL, data)

        # Django ignores the forged row: Ravi's project is completely unchanged...
        victim.refresh_from_db()
        self.assertEqual(victim.title, "Ravi's project")
        self.assertEqual(victim.profile, other_profile)
        # ...and it was not copied or moved into the attacker's profile either.
        self.assertFalse(self.profile.projects.filter(title="Hacked").exists())
        self.assertEqual(Project.objects.count(), 1)