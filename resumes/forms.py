"""Upload form for resumes."""
from django import forms
from django.conf import settings

from .services.pdf_validation import ResumeValidationError, validate_resume_file


class ResumeUploadForm(forms.Form):
    file = forms.FileField(
        label="Resume (PDF)",
        widget=forms.FileInput(attrs={"accept": ".pdf,application/pdf", "class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validated_pdf = None
        # Used by static/js/ui.js to show the chosen file and warn early (the server still checks).
        self.fields["file"].widget.attrs.update({
            "data-max-mb": settings.RESUME_MAX_UPLOAD_MB,
            "data-info-id": "file-info",
            "aria-describedby": "file-help file-info",
        })

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        try:
            self.validated_pdf = validate_resume_file(uploaded)
        except ResumeValidationError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return uploaded