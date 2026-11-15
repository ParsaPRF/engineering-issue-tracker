"""Comment routes. The module owns ``tickets/<id>/comments/`` and ``comments/``."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.comments.api.views import CommentViewSet, TicketCommentsView

router = DefaultRouter()
router.register("comments", CommentViewSet, basename="comment")

urlpatterns = [
    path("tickets/<uuid:ticket_id>/comments/", TicketCommentsView.as_view(), name="ticket-comments"),
    *router.urls,
]