"""Scheduled background tasks for accounts and privacy."""
from celery import shared_task

from .services.privacy import purge_old_data


@shared_task(name="accounts.purge_old_data", ignore_result=True)
def purge_old_data_task() -> dict:
    """Run the retention cleanup (scheduled daily by Celery beat, see settings)."""
    return purge_old_data()