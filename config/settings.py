"""
Django settings for the AI-Powered Profile Onboarder project.

All secrets and environment-specific values are read from environment
variables, loaded from the .env file in the project root.
"""
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# --------------------------------------------------------------------------
# Paths and environment
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from .env into os.environ (does nothing if the file is missing).
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    """Read an environment variable as a boolean ("True", "1", "yes", "on")."""
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment variable as a list of strings."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def env_required(name: str) -> str:
    """Read an environment variable that must be set, or fail with a clear message."""
    value = os.getenv(name)
    if not value:
        raise ImproperlyConfigured(f"Environment variable {name} is not set. Check your .env file.")
    return value


# --------------------------------------------------------------------------
# Core security settings
# --------------------------------------------------------------------------
SECRET_KEY = env_required("DJANGO_SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django built-in apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project apps
    "accounts",
    "resumes",
    "profiles",
    "jobs",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # project-wide templates (base.html etc.)
        "APP_DIRS": True,                  # also look in each app's templates/ folder
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------
# Database (MySQL)
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env_required("DB_NAME"),
        "USER": env_required("DB_USER"),
        "PASSWORD": env_required("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "3306"),
        "CONN_MAX_AGE": 60,  # reuse a connection for up to 60 seconds
        "OPTIONS": {
            "charset": "utf8mb4",
            # Strict mode: MySQL rejects invalid/too-long data instead of
            # silently truncating it.
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "TEST": {
            "CHARSET": "utf8mb4",
            "COLLATION": "utf8mb4_0900_ai_ci",
        },
    }
}

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
# Use our custom User model (email instead of username). Must be set
# BEFORE the first migration.
AUTH_USER_MODEL = "accounts.User"

# Where @login_required sends anonymous users, and where to go after login/logout.
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "profiles:me"
LOGOUT_REDIRECT_URL = "home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Internationalization
# --------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True  # store datetimes in UTC, display in TIME_ZONE

# --------------------------------------------------------------------------
# Static files (CSS, JS, images that are part of the site)
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]  # where we write our CSS/JS
STATIC_ROOT = BASE_DIR / "staticfiles"    # where collectstatic gathers files for deployment

# --------------------------------------------------------------------------
# Media files (user uploads such as resumes)
# These are NOT served publicly; access goes through permission-checked views.
# --------------------------------------------------------------------------
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------------------------------------------------------
# Resume upload limits
# --------------------------------------------------------------------------
RESUME_MAX_UPLOAD_MB = int(os.getenv("RESUME_MAX_UPLOAD_MB", "5"))
RESUME_MAX_PAGES = int(os.getenv("RESUME_MAX_PAGES", "10"))
# Fewer visible characters than this per page => treat the PDF as scanned.
RESUME_MIN_TEXT_CHARS_PER_PAGE = 50

# --------------------------------------------------------------------------
# AI resume parsing (OpenAI)
# --------------------------------------------------------------------------
# Not required at startup, so tests and local work run without a key.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
OPENAI_TIMEOUT_SECONDS = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
# Maximum characters of resume text sent to the AI (limits cost).
RESUME_MAX_AI_INPUT_CHARS = 20_000
# Safety: automated tests must NEVER call the real (paid) AI service.
if len(sys.argv) > 1 and sys.argv[1] == "test":
    OPENAI_API_KEY = ""
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Messages: map Django's "error" level to Bootstrap's "danger" CSS class
# --------------------------------------------------------------------------
from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {message_constants.ERROR: "danger"}

# --------------------------------------------------------------------------
# Email
# Development default: emails are printed in the runserver terminal.
# Part B switches to real SMTP through .env (no code change).
# --------------------------------------------------------------------------
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND") or "django.core.mail.backends.console.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT") or "587")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_TIMEOUT = 20  # seconds; never let a slow mail server hang a request forever
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or "Profile Onboarder <noreply@localhost>"

# Used to build absolute links in emails (works later in background tasks too).
SITE_URL = os.getenv("SITE_URL") or "http://127.0.0.1:8000"

# How long set-password and reset links stay valid.
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT_HOURS") or "48") * 3600
# ---------------------------------------------------------------------------
# Celery: background tasks (Phase 11)
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or "redis://localhost:6379/1"
CELERY_RESULT_EXPIRES = 60 * 60 * 24          # delete stored results after 1 day
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]              # never pickle: unsafe with untrusted messages
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True                  # remove a message only after the task finished
CELERY_WORKER_PREFETCH_MULTIPLIER = 1         # take one slow AI task at a time
CELERY_TASK_SOFT_TIME_LIMIT = 120             # seconds; longer than OPENAI_TIMEOUT_SECONDS
CELERY_TASK_TIME_LIMIT = 180
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_ALWAYS_EAGER = (
    os.getenv("CELERY_TASK_ALWAYS_EAGER", "False").strip().lower() in {"1", "true", "yes"}
)
CELERY_TASK_EAGER_PROPAGATES = True           # in eager mode, errors are raised, not hidden

# Tests never need Redis or a worker: tasks run immediately in the test process.
if len(sys.argv) > 1 and sys.argv[1] == "test":
    CELERY_TASK_ALWAYS_EAGER = True

# ---------------------------------------------------------------------------
# Faster tests (Phase 12)
# ---------------------------------------------------------------------------
if len(sys.argv) > 1 and sys.argv[1] == "test":
    # Real password hashing is slow ON PURPOSE (about a million rounds) to stop attackers.
    # Tests create hundreds of users, so they use a fast hasher. Never used outside tests.
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# ---------------------------------------------------------------------------
# Security hardening (Phase 12B)
# Off by default for local development (no HTTPS on 127.0.0.1).
# Switched on in production through .env, without any code change.
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", default=False)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS") or "0")
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
# Behind a reverse proxy (Phase 14) the proxy tells Django the original request used HTTPS.
if env_bool("DJANGO_BEHIND_HTTPS_PROXY", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Always on (also locally):
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True        # JavaScript can never read the session cookie
SESSION_COOKIE_AGE = 60 * 60 * 8      # log out automatically after 8 hours

# ---------------------------------------------------------------------------
# Login rate limiting (Phase 12B2)
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = ["accounts.backends.ThrottledModelBackend"]

# Local development: in-memory cache (one process). Phase 14: Redis, shared by all processes.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "onboarder"}
}
# Tests: no cache, so failed logins in one test never lock out another test.
# The rate-limit tests switch on a real cache for themselves.
if len(sys.argv) > 1 and sys.argv[1] == "test":
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}   
# ---------------------------------------------------------------------------
# Data retention (Phase 12C) - explained on the privacy page
# ---------------------------------------------------------------------------
UNCLAIMED_DATA_RETENTION_DAYS = int(os.getenv("UNCLAIMED_DATA_RETENTION_DAYS") or "30")
AUDIT_LOG_RETENTION_DAYS = int(os.getenv("AUDIT_LOG_RETENTION_DAYS") or "365")

# ---------------------------------------------------------------------------
# Deployment (Phase 14)
# ---------------------------------------------------------------------------
from celery.schedules import crontab  # noqa: E402

TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

# WhiteNoise serves static files. In production every file gets a content hash in its
# name (style.3f2a1b.css), so browsers may cache it forever. Locally and in tests the
# plain storage is used, so no "collectstatic" is needed.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG and not TESTING
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

import warnings  # noqa: E402

# Locally the "staticfiles" folder only exists after collectstatic (done in the Docker build).
warnings.filterwarnings("ignore", message=r"No directory at")

# Needed when the site runs on a real HTTPS domain, e.g. https://onboarder.example.com
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Health checks from the platform may use plain HTTP inside the server.
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]

# Containers keep no log files: everything goes to the console (docker compose logs).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL") or ("CRITICAL" if TESTING else "INFO"),
    },
}

# Celery beat: the retention cleanup runs every night (see the privacy page).
CELERY_BEAT_SCHEDULE = {
    "purge-old-data-daily": {
        "task": "accounts.purge_old_data",
        "schedule": crontab(hour=3, minute=30),
    },
}