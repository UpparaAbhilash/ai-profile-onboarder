from django import forms


class ApplicationForm(forms.Form):
    cover_note = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 5, "class": "form-control", "maxlength": 2000}),
    )