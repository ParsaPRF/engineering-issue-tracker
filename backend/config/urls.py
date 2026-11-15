"""Root URL configuration.

Two trees only:

* ``/api/v1/...`` — the versioned REST API (ADR-013). It is composed from each app's
  ``api/urls.py``. Every app owns **distinct route prefixes** (``auth/…``, ``projects/…``,
  ``tickets/…``, …), so including them all at the same level cannot shadow another app's routes.
* ``/api/schema/``, ``/api/docs/``, ``/api/redoc/`` — generated OpenAPI documentation.
* ``/admin/`` — Django admin for operational tasks.
* ``/health/`` — liveness/readiness probe used by Docker Compose and load balancers.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from common.views import HealthView

api_v1_patterns = [
    path("", include("apps.accounts.api.urls")),
    path("", include("apps.projects.api.urls")),
    path("", include("apps.tickets.api.urls")),
    path("", include("apps.workflows.api.urls")),
    path("", include("apps.comments.api.urls")),
    path("", include("apps.attachments.api.urls")),
    path("", include("apps.notifications.api.urls")),
    path("", include("apps.audit.api.urls")),
    path("", include("apps.reports.api.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "v1"))),
    path("health/", HealthView.as_view(), name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    # Development only. In production Nginx serves /media (public, non-sensitive) while every
    # attachment is streamed by the authorising download view in every environment (ADR-010).
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
