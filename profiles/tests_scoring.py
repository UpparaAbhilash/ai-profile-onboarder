"""Tests for the profile scoring engine."""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from profiles.tests_import import make_parsed_resume

from .models import Achievement, JobSeekerProfile, Project, Skill
from .services.profile_import import import_profile_from_resume
from .services.scoring import calculate_score, update_profile_score
from .tests_edit import form_data
from .tests_status import User, make_complete_profile


def add_full_project(profile, title):
    return Project.objects.create(
        profile=profile,
        title=title,
        description="A detailed description of this project.",
        start_date=date(2023, 1, 1),
        role="Developer",
    )


def make_perfect_profile():
    user, profile = make_complete_profile()
    profile.experience_summary = "Python developer building Django web applications. " * 3
    profile.total_experience_months = 60
    profile.preferred_roles = ["Backend Developer"]
    profile.save()
    for i in range(7):  # 3 skills already exist -> 10 in total
        profile.skills.add(Skill.objects.create(name=f"Skill {i}"))
    for i in range(3):
        add_full_project(profile, f"Project {i}")
    Achievement.objects.create(profile=profile, kind=Achievement.Kind.CERTIFICATION, title="AWS")
    Achievement.objects.create(profile=profile, kind=Achievement.Kind.AWARD, title="Hackathon winner")
    return user, profile


class ScoreCalculationTests(TestCase):
    def test_empty_profile_scores_zero_with_tips(self):
        user = User.objects.create_user(email="empty@example.com")
        result = calculate_score(JobSeekerProfile.objects.create(user=user))
        self.assertEqual(result.total, 0)
        self.assertEqual(len(result.tips), 5)

    def test_complete_basic_profile(self):
        _, profile = make_complete_profile()
        result = calculate_score(profile)
        points = {key: item["points"] for key, item in result.breakdown.items()}
        self.assertEqual(points, {
            "completeness": 30,
            "experience": 10,   # 5 type + 0 summary + 5 for 2.5 years
            "skills": 6,        # 3 skills x 2
            "projects": 0,
            "achievements": 0,
            "preferences": 5,   # location yes, role no
        })
        self.assertEqual(result.total, 51)

    def test_perfect_profile_scores_100_without_tips(self):
        _, profile = make_perfect_profile()
        result = calculate_score(profile)
        self.assertEqual(result.total, 100)
        self.assertEqual(result.tips, [])

    def test_project_quality_matters(self):
        _, profile = make_complete_profile()
        Project.objects.create(profile=profile, title="Title only")
        self.assertEqual(calculate_score(profile).breakdown["projects"]["points"], 1)
        add_full_project(profile, "Full project")
        self.assertEqual(calculate_score(profile).breakdown["projects"]["points"], 6)

    def test_only_the_best_three_projects_count(self):
        _, profile = make_complete_profile()
        for i in range(4):
            add_full_project(profile, f"Project {i}")
        self.assertEqual(calculate_score(profile).breakdown["projects"]["points"], 15)

    def test_experience_is_capped_at_five_years(self):
        _, profile = make_complete_profile()
        profile.total_experience_months = 240  # 20 years
        profile.save()
        self.assertEqual(calculate_score(profile).breakdown["experience"]["points"], 15)

    def test_tips_are_sorted_by_points(self):
        _, profile = make_complete_profile()
        points = [tip.points for tip in calculate_score(profile).tips]
        self.assertEqual(points, sorted(points, reverse=True))


class ScoreStorageTests(TestCase):
    def test_update_profile_score_saves_score_and_breakdown(self):
        _, profile = make_complete_profile()
        update_profile_score(profile)
        profile.refresh_from_db()
        self.assertEqual(profile.score, 51)
        self.assertEqual(profile.score_breakdown["skills"]["points"], 6)
        self.assertIsNotNone(profile.score_updated_at)

    def test_editing_the_profile_recalculates_the_score(self):
        user, profile = make_complete_profile()
        self.client.force_login(user)
        self.client.post(reverse("profiles:edit"), form_data())
        profile.refresh_from_db()
        self.assertGreater(profile.score, 0)
        self.assertIsNotNone(profile.score_updated_at)

    def test_import_from_resume_sets_the_score(self):
        user = User.objects.create_user(email="asha.rao@example.com")
        profile, _ = import_profile_from_resume(make_parsed_resume(user), user)
        profile.refresh_from_db()
        self.assertGreater(profile.score, 0)

    def test_profile_page_shows_score_and_tips(self):
        user, _ = make_complete_profile()
        self.client.force_login(user)
        response = self.client.get(reverse("profiles:me"))
        self.assertContains(response, "Profile score")
        self.assertContains(response, "51<span")
        self.assertContains(response, "How to improve")

    def test_recalculate_scores_command(self):
        _, profile = make_complete_profile()  # created directly: stored score is still 0
        out = StringIO()
        call_command("recalculate_scores", stdout=out)
        profile.refresh_from_db()
        self.assertEqual(profile.score, 51)
        self.assertIn("Recalculated 1 profile score(s)", out.getvalue())