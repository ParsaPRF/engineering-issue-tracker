"""Test settings.

Goals: the suite runs with **no external services**, is fast, and cannot touch real systems.

* SQLite (ADR-008), using Django's default in-memory test database for speed. Behaviour that
  needs PostgreSQL row locking (concurrency) is covered by ``@pytest.mark.postgres`` tests that
  are skipped here — see docs/development/testing-guide.md.
* A fast password hasher: tests create users by the dozen and PBKDF2 would dominate runtime.
* Celery runs eagerly (ADR-009), so task logic executes inside the test and is asserted inline.
* Attachments are written to a throwaway directory, never to a real bucket.
"""

import tempfile
from pathlib import Path

from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(tempfile.gettempdir()) / "eng_tracker.sqlite3",
        "OPTIONS": {"timeout": 30},
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Filesystem storage in a temporary directory keeps the repository clean.
STORAGE_BACKEND = "local"
MEDIA_ROOT = Path(tempfile.gettempdir()) / "eng_tracker_test_media"

# Throttling is disabled by default so unrelated tests are not rate limited; the dedicated
# throttle test re-enables it with a low rate.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {"auth": None, "attachment_upload": None},
}

TICKET_KEY_MAX_RETRIES = 5
COMMENT_EDIT_WINDOW_MINUTES = 30
ALLOW_SELF_REGISTRATION = True

LOGGING = {
    **LOGGING,  # noqa: F405
    "root": {"handlers": ["console"], "level": "ERROR"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "apps": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
