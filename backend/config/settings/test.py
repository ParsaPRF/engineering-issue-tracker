"""Test settings.

Goals: the suite runs with **no external services** by default, is fast, and cannot touch real
systems — while still being able to run against **PostgreSQL** when the environment asks for it.

* ``DB_ENGINE=sqlite`` (default): SQLite file, no services needed (ADR-008). Tests that need
  PostgreSQL row locking are marked ``postgres`` and skipped with a printed reason.
* ``DB_ENGINE=postgres``: the same suite runs against a real PostgreSQL. This is what CI uses, so
  the ``postgres``-marked tests actually execute somewhere instead of being skipped forever — a
  skip that is never run is indistinguishable from a deleted test.
* A fast password hasher: tests create users by the dozen and PBKDF2 would dominate runtime.
* Celery runs eagerly (ADR-009), so task logic executes inside the test and is asserted inline.
* Attachments are written to a throwaway directory, never to a real bucket.
"""

import tempfile
from pathlib import Path

from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK, env

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

if env("DB_ENGINE", default="sqlite").lower() == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", default="eng_tracker"),
            "USER": env("POSTGRES_USER", default="eng_tracker"),
            "PASSWORD": env("POSTGRES_PASSWORD", default=""),
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env("POSTGRES_PORT", default="5432"),
            "OPTIONS": {"connect_timeout": 5},
        }
    }
else:
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
