"""Filter form for the candidate search."""
from django import forms

from profiles.forms import BootstrapFormMixin, split_comma_list
from profiles.models import JobSeekerProfile

SORT_CHOICES = [
    ("score", "Highest score"),
    ("newest", "Newest"),
    ("experience", "Most experience"),
    ("name", "Name (A–Z)"),
]
MAX_SKILL_FILTERS = 10


class CandidateFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(
        label="Search", required=False, max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Name, email or role"}),
    )
    skills = forms.CharField(
        label="Skills (all required)", required=False, max_length=300,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Python, Django"}),
    )
    city = forms.CharField(
        label="City", required=False, max_length=100,
        help_text="Current city or a preferred location.",
    )
    status = forms.ChoiceField(
        label="Status", required=False,
        choices=[("", "Any status")] + list(JobSeekerProfile.Status.choices),
    )
    experience_type = forms.ChoiceField(
        label="Experience type", required=False,
        choices=[("", "Any")] + list(JobSeekerProfile.ExperienceType.choices),
    )
    min_years = forms.IntegerField(label="Min. years", required=False, min_value=0, max_value=60)
    max_years = forms.IntegerField(label="Max. years", required=False, min_value=0, max_value=60)
    min_score = forms.IntegerField(label="Min. score", required=False, min_value=0, max_value=100)
    sort = forms.ChoiceField(label="Sort by", required=False, choices=SORT_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_skills(self):
        skills = split_comma_list(self.cleaned_data.get("skills", ""))
        if len(skills) > MAX_SKILL_FILTERS:
            raise forms.ValidationError(f"Filter by at most {MAX_SKILL_FILTERS} skills.")
        return skills

    def clean(self):
        cleaned = super().clean()
        low, high = cleaned.get("min_years"), cleaned.get("max_years")
        if low is not None and high is not None and low > high:
            self.add_error("max_years", "Maximum years cannot be smaller than minimum years.")
        return cleaned