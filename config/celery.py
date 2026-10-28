"""Celery application for the AI Profile Onboarder."""
import os

from celery import Celery

# The worker is started without manage.py, so it must know where the settings are.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")

# Read every setting that starts with CELERY_ from Django's settings.py.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Find tasks.py in every installed app (resumes/tasks.py in Part B).
app.autodiscover_tasks()


@app.task(name="config.ping")
def ping():
    """Health check: proves that broker, worker and result backend work together."""
    return "pong"