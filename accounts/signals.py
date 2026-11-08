"""Login signals: link waiting resumes, and count failed logins for rate limiting."""
from django.contrib import messages
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from .services.login_throttle import client_ip, record_failure, reset
from .services.onboarding import link_pending_resumes


@receiver(user_logged_in)
def link_resumes_on_login(sender, request, user, **kwargs):
    linked = link_pending_resumes(user)
    if linked and request is not None:
        messages.success(
            request,
            f"{linked} uploaded resume(s) were linked to your account.",
            fail_silently=True,  # some logins (e.g. in tests) have no message storage
        )


@receiver(user_logged_in)
def reset_failed_logins(sender, request, user, **kwargs):
    reset(user.email)


@receiver(user_login_failed)
def count_failed_login(sender, credentials, request=None, **kwargs):
    # Django masks the password in "credentials"; we only use the email.
    record_failure(credentials.get("username"), client_ip(request))