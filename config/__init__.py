# Load Celery whenever Django starts, so tasks (.delay) use our configuration.
from .celery import app as celery_app

__all__ = ("celery_app",)