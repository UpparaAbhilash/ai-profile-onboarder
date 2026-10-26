"""Forms for candidates to review and correct their profile."""
import re
from datetime import date

from django import forms
from django.forms import inlineformset_factory

from .models import Achievement, JobSeekerProfile, Project
from .services.profile_import import get_or_create_skill

MAX_SKILLS = 50


class BootstrapFormMixin:
    """Add Bootstrap CSS classes to every widget, so templates can stay simple."""

    def apply_bootstrap(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, forms.Select):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


def split_comma_list(value: str) -> list[str]:
    """'Python, django , Django' -> ['Python', 'django'] (duplicates ignored, case-insensitive)."""
    seen, items = set(), []
    for part in value.split(","):
        item = " ".join(part.split())
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            items.append(item)
    return items


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    # Fields that do not exist in the database; converted in clean()/save().
    experience_years = forms.IntegerField(
        label="Experience (years)", required=False, min_value=0, max_value=60
    )
    experience_months = forms.IntegerField(
        label="Experience (months)", required=False, min_value=0, max_value=11
    )
    skills_text = forms.CharField(
        label="Skills",
        required=False,
        help_text="Separate skills with commas, e.g. Python, Django, MySQL.",
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    preferred_roles_text = forms.CharField(
        label="Preferred roles", required=False, help_text="Separate with commas."
    )
    preferred_locations_text = forms.CharField(
        label="Preferred locations", required=False, help_text="Separate with commas."
    )
    # Declared here (not taken from the model) so a full 12-digit number gets
    # a clear message instead of a generic "too long" error.
    aadhaar_last4 = forms.CharField(
        label="Aadhaar (last 4 digits only)",
        required=False,
        max_length=20,
        help_text="Optional. We never store the full number.",
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}),
    )

    field_order = [
        "first_name", "last_name", "surname", "phone", "date_of_birth", "aadhaar_last4",
        "current_city", "professional_role", "current_company", "experience_type",
        "experience_years", "experience_months", "skills_text",
        "preferred_roles_text", "preferred_locations_text", "experience_summary",
    ]

    class Meta:
        model = JobSeekerProfile
        fields = [
            "first_name", "last_name", "surname", "phone", "date_of_birth",
            "experience_type", "current_company", "professional_role",
            "current_city", "experience_summary",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "experience_summary": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = self.instance
        if profile.pk:
            months = profile.total_experience_months
            if months is not None:
                self.initial["experience_years"] = months // 12
                self.initial["experience_months"] = months % 12
            self.initial["skills_text"] = ", ".join(profile.skills.values_list("name", flat=True))
            self.initial["preferred_roles_text"] = ", ".join(profile.preferred_roles)
            self.initial["preferred_locations_text"] = ", ".join(profile.preferred_locations)
        self.apply_bootstrap()

    # ----- single-field validation ---------------------------------------
    def clean_phone(self):
        raw = (self.cleaned_data.get("phone") or "").strip()
        if not raw:
            return ""
        digits = re.sub(r"\D", "", raw)
        if not 7 <= len(digits) <= 15:
            raise forms.ValidationError("A phone number must have 7 to 15 digits.")
        return ("+" if raw.startswith("+") else "") + digits

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        if dob:
            today = date.today()
            youngest = date(today.year - 14, today.month, min(today.day, 28))
            if dob.year < 1940 or dob > youngest:
                raise forms.ValidationError("Please enter a realistic date of birth.")
        return dob

    def clean_aadhaar_last4(self):
        digits = re.sub(r"\D", "", self.cleaned_data.get("aadhaar_last4") or "")
        if not digits:
            return ""
        if len(digits) != 4:
            # The full number is rejected and therefore never saved.
            raise forms.ValidationError(
                "Enter only the last 4 digits. The full Aadhaar number is never stored."
            )
        return digits

    def clean_skills_text(self):
        skills = split_comma_list(self.cleaned_data.get("skills_text", ""))
        if len(skills) > MAX_SKILLS:
            raise forms.ValidationError(f"Please list at most {MAX_SKILLS} skills.")
        too_long = [s for s in skills if len(s) > 100]
        if too_long:
            raise forms.ValidationError("Each skill can have at most 100 characters.")
        return skills

    def clean_preferred_roles_text(self):
        return split_comma_list(self.cleaned_data.get("preferred_roles_text", ""))

    def clean_preferred_locations_text(self):
        return split_comma_list(self.cleaned_data.get("preferred_locations_text", ""))

    # ----- validation across fields --------------------------------------
    def clean(self):
        cleaned = super().clean()
        years = cleaned.get("experience_years")
        months = cleaned.get("experience_months")
        if years is None and months is None:
            cleaned["total_experience_months"] = None
        else:
            cleaned["total_experience_months"] = (years or 0) * 12 + (months or 0)
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.aadhaar_last4 = self.cleaned_data["aadhaar_last4"]
        profile.total_experience_months = self.cleaned_data["total_experience_months"]
        profile.preferred_roles = self.cleaned_data["preferred_roles_text"]
        profile.preferred_locations = self.cleaned_data["preferred_locations_text"]
        if commit:
            profile.save()
            profile.skills.set(
                [get_or_create_skill(name) for name in self.cleaned_data["skills_text"]]
            )
        return profile


class ProjectForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ["title", "role", "start_date", "end_date", "description", "activities"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 2}),
            "activities": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date cannot be before the start date.")
        return cleaned


class AchievementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Achievement
        fields = ["kind", "title", "issuer", "year"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_year(self):
        year = self.cleaned_data.get("year")
        if year is not None and not 1950 <= year <= date.today().year + 1:
            raise forms.ValidationError("Please enter a realistic year.")
        return year


ProjectFormSet = inlineformset_factory(
    JobSeekerProfile, Project, form=ProjectForm,
    extra=1, can_delete=True, max_num=30, validate_max=True,
)
AchievementFormSet = inlineformset_factory(
    JobSeekerProfile, Achievement, form=AchievementForm,
    extra=1, can_delete=True, max_num=30, validate_max=True,
)