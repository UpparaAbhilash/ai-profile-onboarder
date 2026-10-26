"""Candidate profiles, skills, projects, achievements and status history."""
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q

phone_validator = RegexValidator(
    regex=r"^\+?[0-9\s\-]{7,20}$",
    message="Enter a valid phone number (digits, spaces, dashes, optional leading +).",
)
aadhaar_last4_validator = RegexValidator(
    regex=r"^\d{4}$",
    message="Enter exactly 4 digits.",
)


class Skill(models.Model):
    # Unique and case-insensitive thanks to the utf8mb4_0900_ai_ci collation.
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        self.name = " ".join(self.name.split())  # trim and collapse spaces
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class JobSeekerProfile(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        REVIEWED = "reviewed", "Reviewed"
        OPEN_TO_WORK = "open_to_work", "Open to Work"
        NOT_INTERESTED = "not_interested", "Not Interested"

    class ExperienceType(models.TextChoices):
        FRESHER = "fresher", "Fresher"
        EXPERIENCED = "experienced", "Experienced"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    source_resume = models.ForeignKey(
        "resumes.Resume",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profiles",
    )

    # Personal details
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    surname = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    date_of_birth = models.DateField(null=True, blank=True)  # sensitive: restricted display
    aadhaar_last4 = models.CharField(  # never store the full Aadhaar number
        max_length=4, blank=True, validators=[aadhaar_last4_validator]
    )

    # Professional details
    experience_type = models.CharField(
        max_length=20, choices=ExperienceType.choices, blank=True
    )
    total_experience_months = models.PositiveSmallIntegerField(null=True, blank=True)
    current_company = models.CharField(max_length=200, blank=True)
    professional_role = models.CharField(max_length=150, blank=True)  # e.g. "Java Developer"
    skills = models.ManyToManyField(Skill, blank=True, related_name="profiles")
    experience_summary = models.TextField(blank=True)

    # Location and preferences
    current_city = models.CharField(max_length=100, blank=True, db_index=True)
    preferred_locations = models.JSONField(default=list, blank=True)
    preferred_roles = models.JSONField(default=list, blank=True)

    # Workflow and scoring
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CREATED, db_index=True
    )
    score = models.PositiveSmallIntegerField(default=0, db_index=True)
    score_breakdown = models.JSONField(default=dict, blank=True)
    score_updated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(score__lte=100), name="profile_score_max_100"),
        ]
        permissions = [
            ("review_profile", "Can review candidate profiles"),
        ]

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.last_name, self.surname]
        return " ".join(p for p in parts if p)

    @property
    def aadhaar_masked(self) -> str:
        return f"XXXX-XXXX-{self.aadhaar_last4}" if self.aadhaar_last4 else ""

    @property
    def total_experience_years(self):
        if self.total_experience_months is None:
            return None
        return round(self.total_experience_months / 12, 1)

    def __str__(self) -> str:
        return self.full_name or self.user.email


class Project(models.Model):
    profile = models.ForeignKey(
        JobSeekerProfile, on_delete=models.CASCADE, related_name="projects"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    role = models.CharField(max_length=150, blank=True)
    activities = models.TextField(blank=True, help_text="Responsibilities, one per line.")
    start_date = models.DateField(null=True, blank=True, help_text="Use the 1st of the month.")
    end_date = models.DateField(null=True, blank=True, help_text="Leave empty if ongoing.")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(start_date__isnull=True)
                    | Q(end_date__isnull=True)
                    | Q(end_date__gte=F("start_date"))
                ),
                name="project_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class Achievement(models.Model):
    class Kind(models.TextChoices):
        CERTIFICATION = "certification", "Certification"
        AWARD = "award", "Award"

    profile = models.ForeignKey(
        JobSeekerProfile, on_delete=models.CASCADE, related_name="achievements"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=200)
    issuer = models.CharField(max_length=200, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["kind", "-year"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.title}"


class StatusHistory(models.Model):
    profile = models.ForeignKey(
        JobSeekerProfile, on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(
        max_length=20, choices=JobSeekerProfile.Status.choices, blank=True
    )
    to_status = models.CharField(max_length=20, choices=JobSeekerProfile.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "status history"

    def __str__(self) -> str:
        return f"{self.profile}: {self.from_status or '—'} → {self.to_status}"