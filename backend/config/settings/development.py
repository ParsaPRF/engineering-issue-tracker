"""Development settings: convenient, still safe by default.

Used by ``manage.py`` and the local ``runserver``. Deliberately does **not** relax security in
ways that hide mistakes: CSRF stays on, sessions stay HttpOnly. It only turns on DEBUG and
permissive cookie flags that require plain HTTP.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0", "testserver"]
)

# The Vite dev server proxies /api to this backend, so normal development is same-origin and
# needs no CORS entry at all. These remain for direct API calls from tools.
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"],
)

# Plain-HTTP development cannot use Secure cookies.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
