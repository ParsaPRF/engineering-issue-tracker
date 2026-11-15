"""Attachment routes. The module owns ``attachments/`` and the ticket/comment sub-resources."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.attachments.api.views import (
    AttachmentViewSet,
    CommentAttachmentsView,
    TicketAttachmentsView,
)

router = DefaultRouter()
router.register("attachments", AttachmentViewSet, basename="attachment")

urlpatterns = [
    path(
        "tickets/<uuid:ticket_id>/attachments/",
        TicketAttachmentsView.as_view(),
        name="ticket-attachments",
    ),
    path(
        "comments/<uuid:comment_id>/attachments/",
        CommentAttachmentsView.as_view(),
        name="comment-attachments",
    ),
    # Explicit route before the router's detail route so ``download`` is not swallowed by ``pk``.
    path(
        "attachments/<uuid:pk>/download/",
        AttachmentViewSet.as_view({"get": "download"}),
        name="attachment-download",
    ),
    *router.urls,
]