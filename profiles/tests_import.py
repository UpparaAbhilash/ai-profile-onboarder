"""Tests for importing parsed resumes into profiles, and the profile pages."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from resumes.models import Resume
from resumes.services.resume_parsing import parse_and_store
from resumes.tests_ai import SAMPLE_RESUME, fake_client, make_resume_data

from .models import Achievement, JobSeekerProfile, Skill
from .services.profile_import import import_profile_from_resume

User = get_user_model()
PASSWORD = "S3cure-pass-123"


def parsed_fields(**overrides):
    fields = {
        "first_name": "Asha",
        "last_name": "Rao",
        "surname": None,
        "email": "asha.rao@example.com",
        "phone": "+919876543210",
        "date_of_birth": "1998-05-14",
        "experience_type": "experienced",
        "total_experience_months": 40,
        "current_company": "Acme Corp",
        "professional_role": "Python Developer",
        "skills": ["Python", "Django"],
        "current_city": "Bengaluru",
        "preferred_locations": ["Berlin"],
        "preferred_roles": [],
        "projects": [
            {
                "title": "Resume Parser",
                "description": "PDF parser",
                "role": "Developer",
                "start_month": "2023-02",
                "end_month": "2023-06",
                "is_ongoing": False,
                "activities": ["Built extraction", "Wrote tests"],
            }
        ],
        "certifications": [{"title": "AWS Cloud Practitioner", "issuer": "Amazon", "year": 2022}],
        "awards": [],
        "experience_summary": "Python developer.",
        "aadhaar_last4": "0123",
    }
    fields.update(overrides)
    return fields


def make_parsed_resume(owner, fields=None):
    return Resume.objects.create(
        owner=owner,
        file="resumes/test/test.pdf",  # the file itself is not needed for these tests
        original_filename="resume.pdf",
        file_size=1000,
        sha256="0" * 64,
        status=Resume.Status.PARSED,
        parsed_data={"fields": fields or parsed_fields(), "warnings": []},
    )


class ProfileImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="asha@example.com", password=PASSWORD)

    def test_creates_profile_with_all_parts(self):
        profile, created = import_profile_from_resume(make_parsed_resume(self.user), self.user)
        self.assertTrue(created)
        self.assertEqual(profile.full_name, "Asha Rao")
        self.assertEqual(profile.date_of_birth, date(1998, 5, 14))
        self.assertEqual(profile.aadhaar_masked, "XXXX-XXXX-0123")
        self.assertEqual(sorted(profile.skills.values_list("name", flat=True)), ["Django", "Python"])
        project = profile.projects.get()
        self.assertEqual(project.start_date, date(2023, 2, 1))
        self.assertEqual(project.activities, "Built extraction\nWrote tests")
        self.assertEqual(profile.achievements.get().kind, Achievement.Kind.CERTIFICATION)
        self.assertEqual(profile.status_history.count(), 1)

    def test_existing_values_are_never_overwritten(self):
        JobSeekerProfile.objects.create(user=self.user, first_name="Ashwini", current_city="Berlin")
        profile, created = import_profile_from_resume(make_parsed_resume(self.user), self.user)
        self.assertFalse(created)
        self.assertEqual(profile.first_name, "Ashwini")  # kept (candidate's value)
        self.assertEqual(profile.current_city, "Berlin")  # kept
        self.assertEqual(profile.last_name, "Rao")  # was empty -> filled

    def test_reimport_does_not_create_duplicates(self):
        resume = make_parsed_resume(self.user)
        import_profile_from_resume(resume, self.user)
        profile, _ = import_profile_from_resume(resume, self.user)
        self.assertEqual(profile.projects.count(), 1)
        self.assertEqual(profile.skills.count(), 2)
        self.assertEqual(profile.achievements.count(), 1)
        self.assertEqual(profile.status_history.count(), 1)

    def test_existing_skill_is_reused_ignoring_case(self):
        Skill.objects.create(name="python")
        import_profile_from_resume(make_parsed_resume(self.user), self.user)
        self.assertEqual(Skill.objects.filter(name__iexact="python").count(), 1)

    def test_ongoing_project_has_no_end_date(self):
        project = dict(parsed_fields()["projects"][0], is_ongoing=True, end_month=None)
        fields = parsed_fields(projects=[project])
        profile, _ = import_profile_from_resume(make_parsed_resume(self.user, fields), self.user)
        self.assertIsNone(profile.projects.get().end_date)

    def test_resume_without_parsed_data_raises(self):
        resume = make_parsed_resume(self.user)
        resume.parsed_data = None
        with self.assertRaises(ValueError):
            import_profile_from_resume(resume, self.user)


class ProfilePageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="asha@example.com", password=PASSWORD)
        self.other = User.objects.create_user(email="ravi@example.com", password=PASSWORD)

    def test_my_profile_requires_login(self):
        response = self.client.get(reverse("profiles:me"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('profiles:me')}")

    def test_user_without_profile_sees_upload_prompt(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("profiles:me")), "don't have a profile yet")

    def test_user_sees_only_own_profile(self):
        JobSeekerProfile.objects.create(user=self.user, first_name="Asha")
        JobSeekerProfile.objects.create(user=self.other, first_name="Ravi")
        self.client.force_login(self.user)
        response = self.client.get(reverse("profiles:me"))
        self.assertContains(response, "Asha")
        self.assertNotContains(response, "Ravi")

    def test_import_view_creates_profile_for_owner(self):
        resume = make_parsed_resume(self.user)
        self.client.force_login(self.user)
        response = self.client.post(reverse("profiles:import_from_resume", args=[resume.pk]))
        self.assertRedirects(response, reverse("profiles:me"))
        self.assertTrue(JobSeekerProfile.objects.filter(user=self.user).exists())

    def test_import_view_gives_404_for_someone_elses_resume(self):
        resume = make_parsed_resume(self.other)
        self.client.force_login(self.user)
        response = self.client.post(reverse("profiles:import_from_resume", args=[resume.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(JobSeekerProfile.objects.filter(user=self.user).exists())

    def test_import_view_rejects_get(self):
        resume = make_parsed_resume(self.user)
        self.client.force_login(self.user)
        response = self.client.get(reverse("profiles:import_from_resume", args=[resume.pk]))
        self.assertEqual(response.status_code, 405)

    def test_login_with_email_and_password(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "asha@example.com", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("profiles:me"))


@override_settings(OPENAI_MODEL="test-model", OPENAI_API_KEY="")
class ParsingCreatesProfileTests(TestCase):
    def test_parsing_an_owned_resume_creates_the_profile(self):
        user = User.objects.create_user(email="asha@example.com", password=PASSWORD)
        resume = Resume.objects.create(
            owner=user,
            file="resumes/test/test.pdf",
            original_filename="resume.pdf",
            file_size=1000,
            sha256="1" * 64,
            status=Resume.Status.EXTRACTED,
            extracted_text=SAMPLE_RESUME,
        )
        parse_and_store(resume, client=fake_client(make_resume_data()))
        profile = JobSeekerProfile.objects.get(user=user)
        self.assertEqual(profile.current_company, "Acme Corp")
        self.assertEqual(profile.source_resume, resume)
        