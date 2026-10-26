"""Link waiting resumes whenever a user logs in (proof that they own the email)."""
from django.contrib import messages
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

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