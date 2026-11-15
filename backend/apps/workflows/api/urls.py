"""Workflow routes.

Two entry points with different shapes, on purpose:

* ``/tickets/<uuid>/transitions/`` and ``/tickets/<uuid>/history/`` — the ticket-scoped operations,
  because a transition is an action *on a ticket*;
* ``/workflows/transitions/?ticket=<uuid>`` and ``/workflows/`` — the read-only catalogue used to
  render the UI and to document the lifecycle.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.workflows.api.views import TicketTransitionsView, TicketTransitionViewSet, WorkflowCatalogueView

router = DefaultRouter()
router.register("tickets", TicketTransitionViewSet, basename="ticket-workflow")

urlpatterns = [
    path("workflows/", WorkflowCatalogueView.as_view(), name="workflow-catalogue"),
    path("workflows/transitions/", TicketTransitionsView.as_view(), name="workflow-transitions"),
    *router.urls,
]