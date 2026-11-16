from django import forms
from django.core.exceptions import ValidationError

from .models import Job

MAX_LOCATIONS = 10


class ApplicationForm(forms.Form):
    cover_note = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 5, "class": "form-control", "maxlength": 2000}),
    )


class AutoApplyForm(forms.Form):
    enabled = forms.BooleanField(
        required=False,
        label="Apply for me automatically",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
    )
    min_match_percent = forms.IntegerField(
        min_value=50, max_value=100, initial=80, label="Minimum skill match (%)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": 5}),
    )
    locations = forms.CharField(
        required=False, max_length=300, label="Locations",
        help_text="Comma-separated, for example: Berlin, Remote. Empty = any location.",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    employment_types = forms.MultipleChoiceField(
        required=False, choices=Job.EmploymentType.choices, label="Job types",
        help_text="Nothing selected = any job type.",
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    max_per_week = forms.IntegerField(
        min_value=1, max_value=5, initial=3, label="Maximum applications per week",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    consent = forms.BooleanField(
        required=False,
        label=(
            "I allow the app to apply for me to jobs that match these rules. "
            "My profile will be shared with those employers."
        ),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    @classmethod
    def from_rule(cls, rule):
        """A form filled with the saved settings."""
        return cls(initial={
            "enabled": rule.enabled,
            "min_match_percent": rule.min_match_percent,
            "locations": ", ".join(rule.locations),
            "employment_types": rule.employment_types,
            "max_per_week": rule.max_per_week,
            "consent": rule.enabled,
        })

    def clean_locations(self):
        """'Berlin, remote ,berlin' -> ['Berlin', 'remote'] (no duplicates, no empty parts)."""
        seen, result = set(), []
        for part in self.cleaned_data["locations"].split(","):
            name = " ".join(part.split())
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                result.append(name)
        if len(result) > MAX_LOCATIONS:
            raise ValidationError(f"Please enter at most {MAX_LOCATIONS} locations.")
        return result

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("enabled") and not cleaned.get("consent"):
            self.add_error("consent", "Please confirm that we may apply for you.")
        return cleaned