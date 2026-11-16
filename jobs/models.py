"""Job listings and candidate applications."""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class Job(models.Model):
    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full-time"
        PART_TIME = "part_time", "Part-time"
        INTERNSHIP = "internship", "Internship"
        CONTRACT = "contract", "Contract"

    title = models.CharField(max_length=200)
    company = models.CharField(max_length=200)
    location = models.CharField(max_length=100, db_index=True)
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    description = models.TextField()
    required_skills = models.ManyToManyField(
        "profiles.Skill", blank=True, related_name="jobs"
    )
    min_experience_months = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} at {self.company}"


class Application(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        SHORTLISTED = "shortlisted", "Shortlisted"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    candidate = models.ForeignKey(
        "profiles.JobSeekerProfile", on_delete=models.CASCADE, related_name="applications"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SUBMITTED, db_index=True
    )
    cover_note = models.TextField(blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-applied_at"]
        constraints = [
            # Duplicate prevention enforced by the database itself.
            models.UniqueConstraint(fields=["job", "candidate"], name="unique_application_per_job"),
        ]

    def __str__(self) -> str:
        return f"{self.candidate} → {self.job}"


class AutoApplyRule(models.Model):
    """The candidate's own rules for automatic applications (Phase 17). Off by default."""

    profile = models.OneToOneField(
        "profiles.JobSeekerProfile", on_delete=models.CASCADE, related_name="auto_apply_rule"
    )
    enabled = models.BooleanField(default=False)
    min_match_percent = models.PositiveSmallIntegerField(
        default=80, validators=[MinValueValidator(50), MaxValueValidator(100)]
    )
    locations = models.JSONField(default=list, blank=True)         # empty list = any location
    employment_types = models.JSONField(default=list, blank=True)  # empty list = any job type
    max_per_week = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    enabled_at = models.DateTimeField(null=True, blank=True)  # when the candidate gave consent
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(min_match_percent__gte=50, min_match_percent__lte=100),
                name="auto_apply_min_match_range",
            ),
            models.CheckConstraint(
                condition=Q(max_per_week__gte=1, max_per_week__lte=5),
                name="auto_apply_max_per_week_range",
            ),
            # "On" is only possible together with the time of consent.
            models.CheckConstraint(
                condition=Q(enabled=False) | Q(enabled_at__isnull=False),
                name="auto_apply_enabled_needs_consent_time",
            ),
        ]

    def __str__(self) -> str:
        return f"Auto-apply for {self.profile} ({'on' if self.enabled else 'off'})"