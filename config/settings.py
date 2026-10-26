"""
Django settings for the AI-Powered Profile Onboarder project.

All secrets and environment-specific values are read from environment
variables, loaded from the .env file in the project root.
"""
import os
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"