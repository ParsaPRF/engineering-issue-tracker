"""ASGI entry point.

Kept for completeness (and future websocket/async needs); the deployed stack runs WSGI.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
