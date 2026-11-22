"""Base settings shared by every environment.

Everything environment-specific lives in ``development.py`` / ``production.py`` / ``test.py``.
Values are read through ``django-environ`` so that configuration is 12-factor: secrets never
live in the repository and behaviour can change per environment without code edits.
"""

from datetime import timedelta
from pathlib import Path

import environ

# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parents[2]
# repository root (holds .env, docker-compose.yml)
PROJECT_ROOT = BASE_DIR.parent

env = environ.Env()
# Only read a file if it exists; in Docker, configuration arrives as real environment variables.
for candidate in (PROJECT_ROOT / ".env", BASE_DIR / ".env"):
    if candidate.exists():
        env.read_env(candidate)

# -----------------------------------------------------------------------------
# Core
# -----------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-development-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# -----------------------------------------------------------------------------
# Applications
# -----------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "storages",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.projects",
    "apps.tickets",
    "apps.workflows",
    "apps.comments",
    "apps.attachments",
    "apps.notifications",
    "apps.audit",
    "apps.reports",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# -----------------------------------------------------------------------------
# Database (ADR-008). PostgreSQL is the target; sqlite is an explicit local fallback.
# -----------------------------------------------------------------------------
DB_ENGINE = env("DB_ENGINE", default="postgres").lower()

if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / env("SQLITE_PATH", default="db.sqlite3"),
            # Needed by the concurrency tests, which use threads.
            "OPTIONS": {"timeout": 20},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", default="eng_tracker"),
            "USER": env("POSTGRES_USER", default="eng_tracker"),
            "PASSWORD": env("POSTGRES_PASSWORD", default=""),
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env("POSTGRES_PORT", default="5432"),
            "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
            "OPTIONS": {"connect_timeout": 5},
        }
    }

# -----------------------------------------------------------------------------
# Authentication
# -----------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

# Session cookie policy: the session id is never readable from JavaScript (ADR-003), while the
# CSRF cookie must stay JS-readable because the SPA sends it back in the X-CSRFToken header.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=60 * 60 * 12)
SESSION_SAVE_EVERY_REQUEST = True
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# -----------------------------------------------------------------------------
# Internationalisation
# -----------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# -----------------------------------------------------------------------------
# Static and media
# -----------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGE_BACKEND = env("STORAGE_BACKEND", default="local").lower()

if STORAGE_BACKEND == "s3":
    # MinIO / any S3-compatible endpoint. The bucket stays private: objects are only ever read
    # through the authorising download view, so no querystring signing is used (ADR-010).
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="eng-tracker-attachments")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
    AWS_S3_USE_SSL = env.bool("AWS_S3_USE_SSL", default=True)
    # Path-style addressing is what every self-hosted S3 implementation (MinIO, SeaweedFS,
    # LocalStack, s3mock, Ceph RGW) expects, and it is the safe default for a custom endpoint.
    AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="path")
    AWS_QUERYSTRING_AUTH = False
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "private, max-age=0"}
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

# -----------------------------------------------------------------------------
# Django REST Framework
# -----------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "common.exceptions.envelope_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth": env("THROTTLE_AUTH_RATE", default="20/min"),
        "attachment_upload": env("THROTTLE_UPLOAD_RATE", default="60/hour"),
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Engineering Issue & Ticket Tracking System API",
    "DESCRIPTION": (
        "Versioned REST API for projects, tickets, the ticket workflow, collaboration, "
        "notifications, audit and reporting. Authentication is session-based; obtain the "
        "`csrftoken` cookie from `/api/v1/auth/csrf/` and send it as the `X-CSRFToken` header "
        "on unsafe requests."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "ENUM_NAME_OVERRIDES": {
        # Module paths must match the real layout: ``tickets`` uses a single ``models.py`` while
        # ``projects`` uses a ``models/`` package. A wrong path here produces a schema warning and
        # duplicate component names, not an exception — so it is easy to miss.
        "TicketTypeEnum": "apps.tickets.models.TicketType",
        "TicketStatusEnum": "apps.tickets.models.TicketStatus",
        "PriorityEnum": "apps.tickets.models.Priority",
        "SeverityEnum": "apps.tickets.models.Severity",
        "SystemRoleEnum": "apps.accounts.roles.SystemRole",
        "ProjectRoleEnum": "apps.projects.models.membership.ProjectRole",
        "NotificationEventEnum": "apps.notifications.models.NotificationEvent",
    },
}

# -----------------------------------------------------------------------------
# CORS. Development uses the Vite proxy (same origin), so this is defence in depth for
# clients that call the API directly. Credentials are never combined with a wildcard origin.
# -----------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
CORS_EXPOSE_HEADERS = ["Content-Disposition"]

# -----------------------------------------------------------------------------
# Cache. Redis in Docker/production, in-process memory locally.
#
# The health endpoint reports which backend is active instead of always claiming "redis", so a
# green probe cannot be mistaken for a verified Redis connection (NFR-3.4).
# -----------------------------------------------------------------------------
CACHE_BACKEND = env("CACHE_BACKEND", default="locmem").lower()
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

if CACHE_BACKEND == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("CACHE_URL", default=REDIS_URL),
            "KEY_PREFIX": "eng_tracker",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "eng-tracker-locmem",
        }
    }

# -----------------------------------------------------------------------------
# Celery (ADR-009)
# -----------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "retry-unsent-notifications": {
        "task": "apps.notifications.tasks.retry_unsent_notifications",
        "schedule": timedelta(minutes=10),
    },
}

# -----------------------------------------------------------------------------
# Business rules (kept in settings so operations can tune them without code changes)
# -----------------------------------------------------------------------------
TICKET_KEY_MAX_RETRIES = env.int("TICKET_KEY_MAX_RETRIES", default=5)
COMMENT_EDIT_WINDOW_MINUTES = env.int("COMMENT_EDIT_WINDOW_MINUTES", default=30)
ATTACHMENT_MAX_BYTES = env.int("ATTACHMENT_MAX_BYTES", default=10 * 1024 * 1024)
ATTACHMENT_ALLOWED_EXTENSIONS = [
    ext.strip().lower().lstrip(".")
    for ext in env.list(
        "ATTACHMENT_ALLOWED_EXTENSIONS",
        default=[
            "png", "jpg", "jpeg", "gif", "webp", "pdf", "txt", "csv", "json", "log",
            "zip", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        ],
    )
    if ext.strip()
]
# SVG and HTML are deliberately absent: they execute script when rendered from our origin.
ATTACHMENT_ALLOWED_CONTENT_TYPES = [
    "image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", "text/plain",
    "text/csv", "application/json", "application/zip", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",
]
ALLOW_SELF_REGISTRATION = env.bool("ALLOW_SELF_REGISTRATION", default=True)

# -----------------------------------------------------------------------------
# Logging: never log credentials, tokens or request bodies (NFR-1.10, FR-8.4)
# -----------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "apps": {"level": env("LOG_LEVEL", default="INFO"), "handlers": ["console"], "propagate": False},
    },
}
