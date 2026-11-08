"""Account views: login with rate limiting, set-password links, privacy and data rights."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from dashboard.models import AuditLog

from .forms import DeleteAccountForm
from .services.data_export import export_as_json
from .services.login_throttle import LOCKOUT_MESSAGE, client_ip, is_locked
from .services.privacy import delete_account


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


@require_GET
def privacy(request):
    return render(request, "accounts/privacy.html", {
        "unclaimed_days": settings.UNCLAIMED_DATA_RETENTION_DAYS,
        "audit_days": settings.AUDIT_LOG_RETENTION_DAYS,
        "session_hours": settings.SESSION_COOKIE_AGE // 3600,
    })


@login_required
@never_cache
@require_GET
def download_my_data(request):
    """GDPR Art. 15/20: a JSON copy of everything stored about the logged-in user."""
    content = export_as_json(request.user)
    AuditLog.objects.create(
        actor=request.user, action="data.exported", ip_address=client_ip(request)
    )
    response = HttpResponse(content, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="my-data-{timezone.localdate():%Y-%m-%d}.json"'
    )
    return response


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def delete_my_account(request):
    """GDPR Art. 17: the user deletes their account and all their data."""
    user = request.user
    if user.is_superuser:
        messages.error(request, "Administrator accounts cannot be deleted here.")
        return redirect("accounts:privacy")

    form = DeleteAccountForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        logout(request)  # end the session first
        delete_account(user, reason="user_request")
        messages.success(request, "Your account and all your data have been deleted.")
        return redirect("home")
    return render(request, "accounts/delete_account.html", {"form": form})