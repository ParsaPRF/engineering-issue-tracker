"""Ticket routes. The module owns the ``tickets/`` and ``labels/`` prefixes.

Note that ``apps.workflows`` also registers under ``tickets/`` (``transitions`` and ``history``).
The routers' dynamic action routes are matched before the generic detail route, and both apps scope
their querysets by permission, so the split is safe and keeps each module's routes with its module.
"""

from rest_framework.routers import DefaultRouter

from apps.tickets.api.views import LabelViewSet, TicketViewSet

router = DefaultRouter()
router.register("tickets", TicketViewSet, basename="ticket")
router.register("labels", LabelViewSet, basename="label")

urlpatterns = [*router.urls]