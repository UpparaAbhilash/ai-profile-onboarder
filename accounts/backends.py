"""Authentication backend that refuses to check passwords while a login is locked."""
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from .services.login_throttle import LOCKOUT_MESSAGE, client_ip, is_locked


class ThrottledModelBackend(ModelBackend):
    """Same as Django's ModelBackend, but blocked during a lockout.

    Because the check lives in the backend, it protects EVERY login form:
    our login page and the Django admin login.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if is_locked(username, client_ip(request)):
            # PermissionDenied stops Django immediately: the password is not even checked.
            raise PermissionDenied(LOCKOUT_MESSAGE)
        return super().authenticate(request, username=username, password=password, **kwargs)