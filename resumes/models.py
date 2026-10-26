"""Uploaded resumes and their extraction / AI parsing results."""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def resume_upload_path(instance, filename):
    """Store each resume under a random name, e.g. resumes/2026/10/<uuid>.pdf.

    The original filename is kept in the database, never in the file path,
    so personal names do not appear on disk or in URLs.
    """
    now = timezone.now()
    return f"resumes/{now:%Y/%m}/{uuid.uuid4().hex}.pdf"


class Resume(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        PARSED = "parsed", "Parsed"
        FAILED = "failed", "Failed"

    # Nullable: the resume is uploaded first, the account is created after parsing.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resumes",
    )
    file = models.FileField(upload_to=resume_upload_path)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="Size in bytes.")
    sha256 = models.CharField(max_length=64, db_index=True)
    page_count = models.PositiveSmallIntegerField(null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.UPLOADED, db_index=True
    )
    extracted_text = models.TextField(blank=True)
    parsed_data = models.JSONField(null=True, blank=True)
    ai_model = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    parsed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.get_status_display()})"