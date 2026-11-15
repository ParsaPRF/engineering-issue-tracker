"""Production settings.

Fail-fast posture: the secret key, allowed hosts and CSRF origins must be provided by the
environment, and the process refuses to start with the development defaults.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

SECRET_KEY = env("DJANGO_SECRET_KEY")  # no default on purpose: fail loudly
if len(SECRET_KEY) < 32:
    raise RuntimeError("DJANGO_SECRET_KEY must be at least 32 characters in production.")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# --- Transport and cookie hardening -----------------------------------------
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --- Error reporting ---------------------------------------------------------
ADMINS = [tuple(pair) for pair in env.list("DJANGO_ADMINS", default=[]) if pair]

LOGGING["root"]["level"] = env("LOG_LEVEL", default="WARNING")  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = env("LOG_LEVEL", default="INFO")  # noqa: F405

# --- Object storage ---------------------------------------------------------
# Production must not keep user uploads on the application container's disk.
STORAGE_BACKEND = env("STORAGE_BACKEND", default="s3").lower()
