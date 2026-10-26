"""Account views. Login/logout/reset use Django's secure built-in views."""
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy


class SetPasswordView(auth_views.PasswordResetConfirmView):
    """Handles both the onboarding link and 'Forgot password?' links."""

    template_name = "accounts/password_reset_confirm.html"
    post_reset_login = True  # log the user in right after setting the password
    success_url = reverse_lazy("profiles:me")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Your password is set and you are logged in.")
        return response