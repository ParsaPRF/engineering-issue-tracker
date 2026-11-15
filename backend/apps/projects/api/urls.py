"""Project routes. The module owns the ``projects/`` and ``components/`` prefixes."""

from rest_framework.routers import DefaultRouter

from apps.projects.api.views import ComponentViewSet, ProjectViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("components", ComponentViewSet, basename="component")

urlpatterns = [*router.urls]
