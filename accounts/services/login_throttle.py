"""Slow down password guessing: lock an email address (and an IP address)
for a while after too many failed logins.

Counters live in Django's cache, never in the database. Keys are SHA-256
hashes, so the cache holds no email addresses or IP addresses in plain text.
"""
import hashlib

from django.core.cache import cache

MAX_FAILURES_PER_EMAIL = 5     # protects one account against guessing
MAX_FAILURES_PER_IP = 20       # protects against one attacker trying many accounts
LOCKOUT_SECONDS = 15 * 60
LOCKOUT_MESSAGE = "Too many failed login attempts. Please wait 15 minutes and try again."


def client_ip(request):
    return request.META.get("REMOTE_ADDR") if request is not None else None


def throttle_key(kind: str, value: str) -> str:
    digest = hashlib.sha256(value.strip().lower().encode()).hexdigest()
    return f"login-failures:{kind}:{digest}"


def _limits(email, ip):
    """(cache key, limit) pairs that apply to this login attempt."""
    pairs = []
    if email:
        pairs.append((throttle_key("email", email), MAX_FAILURES_PER_EMAIL))
    if ip:
        pairs.append((throttle_key("ip", ip), MAX_FAILURES_PER_IP))
    return pairs


def is_locked(email, ip) -> bool:
    return any((cache.get(key) or 0) >= limit for key, limit in _limits(email, ip))


def record_failure(email, ip) -> None:
    for key, _limit in _limits(email, ip):
        cache.add(key, 0, LOCKOUT_SECONDS)  # starts the 15-minute window on the first failure
        try:
            cache.incr(key)
        except ValueError:                   # the key expired between add() and incr()
            cache.set(key, 1, LOCKOUT_SECONDS)


def reset(email) -> None:
    """A successful login clears the counter for that email address."""
    if email:
        cache.delete(throttle_key("email", email))