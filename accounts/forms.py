"""Admin forms for the custom User model."""
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

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