"""Audit routes. The module owns the ``audit/`` prefix."""

from rest_framework.routers import DefaultRouter

from apps.audit.api.views import AuditEventViewSet

router = DefaultRouter()
router.register("audit", AuditEventViewSet, basename="audit-event")

urlpatterns = [*router.urls]
