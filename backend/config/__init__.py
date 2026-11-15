"""Project configuration package.

Importing the Celery application here means ``celery -A config worker`` works and that
``@shared_task`` functions are bound to the same app that the Django process uses.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
