"""Account views. Login/logout/reset use Django's secure built-in views."""
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

from .services.login_throttle import LOCKOUT_MESSAGE, client_ip, is_locked


class ThrottledLoginView(auth_views.LoginView):
    """Django's login view, plus a clear message (HTTP 429) during a lockout."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def form_invalid(self, form):
        email = self.request.POST.get("username", "")
        if is_locked(email, client_ip(self.request)):
            context = self.get_context_data(form=form, lockout_message=LOCKOUT_MESSAGE)
            return self.render_to_response(context, status=429)
        return super().form_invalid(form)


class SetPasswordView(auth_views.PasswordResetConfirmView):
    """Handles both the onboarding link and 'Forgot password?' links."""

    template_name = "accounts/password_reset_confirm.html"
    post_reset_login = True  # log the user in right after setting the password
    success_url = reverse_lazy("profiles:me")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Your password is set and you are logged in.")
        return response