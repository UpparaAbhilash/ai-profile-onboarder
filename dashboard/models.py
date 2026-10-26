"""Audit log for important actions (status changes, reviews, deletions)."""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,  # keep the log even if the user is deleted
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=100, db_index=True)  # e.g. "profile.status_changed"

    # Generic relation: the log entry can point to ANY model instance.
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    object_id = models.CharField(max_length=64, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self) -> str:
        who = self.actor.email if self.actor else "system"
        return f"{self.created_at:%Y-%m-%d %H:%M} {who}: {self.action}"