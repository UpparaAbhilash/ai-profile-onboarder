"""Small template helpers for a consistent UI.

Use in a template with:  {% load ui %}
"""
from django import template

register = template.Library()

# One colour per status, used on every page (candidate, reviewer and admin views).
STATUS_COLORS = {
    # Resume
    "uploaded": "secondary",
    "processing": "warning",
    "extracted": "warning",
    "parsed": "success",
    "failed": "danger",
    # Profile
    "created": "secondary",
    "reviewed": "info",
    "open_to_work": "success",
    "not_interested": "dark",
    # Application
    "submitted": "primary",
    "under_review": "info",
    "shortlisted": "success",
    "rejected": "danger",
    "withdrawn": "light border",
}


@register.filter
def status_color(status) -> str:
    """'shortlisted' -> 'success', used as class="badge text-bg-{{ status|status_color }}"."""
    return STATUS_COLORS.get(str(status), "secondary")