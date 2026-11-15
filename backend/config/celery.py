"""Celery application.

The worker is started with ``celery -A config worker -l info``. Task discovery is explicit
(``autodiscover_tasks``) so that adding a ``tasks.py`` to a new app is enough to register it.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("eng_tracker")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:  # pragma: no cover - diagnostics only
    """Trivial task used to prove the worker is alive: ``debug_task.delay()``."""
    return f"celery ok: {self.request.id}"
