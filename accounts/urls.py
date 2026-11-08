"""Login, logout, password reset and set-password links."""
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import EmailPasswordResetForm

app_name = "accounts"

urlpatterns = [
    path("login/", views.ThrottledLoginView.as_view(), name="login"),
    path("privacy/", views.privacy, name="privacy"),
    path("my-data/", views.download_my_data, name="my_data"),
    path("delete/", views.delete_my_account, name="delete_account"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/email/password_reset_email.txt",
            subject_template_name="accounts/email/password_reset_subject.txt",
            form_class=EmailPasswordResetForm,
            success_url=reverse_lazy("accounts:password_reset_done"),
            extra_email_context={"valid_hours": settings.PASSWORD_RESET_TIMEOUT // 3600},
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path("reset/<uidb64>/<token>/", views.SetPasswordView.as_view(), name="password_reset_confirm"),
]