"""Operational endpoints.

``/health/`` is intentionally unauthenticated: Docker Compose, load balancers and uptime monitors
need it, and it exposes no business data.

Honesty matters more than a green light here: the endpoint reports the **configured** cache
backend, and only probes Redis when Redis is actually the backend. A probe that always says
"redis: ok" while the project is running on an in-process cache would be worse than no probe
(NFR-3.4).
"""

from __future__ import annotations

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness/readiness probe: ``200`` when the database is reachable, ``503`` otherwise."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(exclude=True)
    def get(self, request):
        cache_backend = getattr(settings, "CACHE_BACKEND", "locmem")
        checks: dict[str, str] = {
            "database": "ok",
            "cache_backend": cache_backend,
        }
        healthy = True

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception as exc:  # pragma: no cover - depends on infrastructure
            checks["database"] = f"error: {type(exc).__name__}"
            healthy = False

        if cache_backend == "redis":
            try:
                from django.core.cache import cache

                cache.set("health:ping", "1", timeout=5)
                checks["redis"] = "ok" if cache.get("health:ping") == "1" else "degraded"
            except Exception as exc:  # pragma: no cover - depends on infrastructure
                checks["redis"] = f"error: {type(exc).__name__}"
        else:
            # Explicitly not verified rather than assumed healthy.
            checks["redis"] = "not configured"

        payload = {"status": "ok" if healthy else "unhealthy", "checks": checks}
        return Response(
            payload,
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
