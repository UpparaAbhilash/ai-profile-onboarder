"""Forms for the custom User model and password reset."""
from django import forms
from django.contrib.auth.forms import AdminUserCreationForm, PasswordResetForm, UserChangeForm

from .models import User


class CustomUserCreationForm(AdminUserCreationForm):
    """Form used on the admin 'Add user' page."""

    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email",)


class CustomUserChangeForm(UserChangeForm):
    """Form used on the admin 'Change user' page."""

    class Meta(UserChangeForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name")


class EmailPasswordResetForm(PasswordResetForm):
    """Password reset that also works for accounts created from a resume.

    Django's default form skips users with an unusable password. Our onboarded
    users have exactly that until they click their first link, so if that email
    gets lost they must still be able to request a new link.
    """

    def get_users(self, email):
        return User._default_manager.filter(email__iexact=email, is_active=True)


class DeleteAccountForm(forms.Form):
    """Re-authentication before a destructive action: password + explicit confirmation."""

    password = forms.CharField(
        label="Your password",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "current-password"}),
    )
    confirm = forms.BooleanField(
        label="I understand that my account and all my data will be deleted permanently.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("The password is not correct.")
        return password