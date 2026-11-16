"""Auto-apply settings (Phase 17A). The candidate's consent and rules.

This module only SAVES the rules. Applying happens in the nightly job (Phase 17B).
"""
from django.db import transaction
from django.utils import timezone

from dashboard.models import AuditLog
from profiles.models import JobSeekerProfile
from profiles.services.completeness import missing_required_fields

from ..models import AutoApplyRule

SETTING_FIELDS = ("min_match_percent", "locations", "employment_types", "max_per_week")


class AutoApplyError(Exception):
    """The change is not allowed. The message is safe to show to users."""


def get_rule(profile) -> AutoApplyRule:
    """The saved rule, or an unsaved default rule (opening the page never writes to the database)."""
    return AutoApplyRule.objects.filter(profile=profile).first() or AutoApplyRule(profile=profile)


def check_can_enable(profile) -> None:
    if profile.status == JobSeekerProfile.Status.NOT_INTERESTED:
        raise AutoApplyError(
            "Your availability is 'Not Interested'. Change it to 'Open to Work' to turn on auto-apply."
        )
    missing = missing_required_fields(profile)
    if missing:
        raise AutoApplyError("Please complete your profile first. Missing: " + ", ".join(missing) + ".")


def save_rule(profile, actor, *, enabled: bool, **values) -> AutoApplyRule:
    """Save the rules. Turning auto-apply on, off or changing it while on is audited."""
    if enabled:
        check_can_enable(profile)  # turning it OFF is always allowed

    with transaction.atomic():
        rule, _ = AutoApplyRule.objects.select_for_update().get_or_create(profile=profile)
        was_enabled = rule.enabled
        old_values = {name: getattr(rule, name) for name in SETTING_FIELDS}

        for name in SETTING_FIELDS:
            setattr(rule, name, values[name])
        rule.enabled = enabled

        if enabled and not was_enabled:
            rule.enabled_at = timezone.now()  # the moment of consent
            action = "auto_apply.enabled"
        elif was_enabled and not enabled:
            rule.enabled_at = None
            action = "auto_apply.disabled"
        elif enabled and old_values != {name: getattr(rule, name) for name in SETTING_FIELDS}:
            action = "auto_apply.updated"
        else:
            action = None  # saved while off, or nothing changed

        rule.full_clean(exclude=["profile"])  # model validators, also when called from elsewhere
        rule.save()

        if action:
            details = {name: getattr(rule, name) for name in SETTING_FIELDS} if enabled else {}
            AuditLog.objects.create(actor=actor, action=action, target=rule, details=details)
    return rule