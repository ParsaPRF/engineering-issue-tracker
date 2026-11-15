"""Notification API: the caller's own inbox, read and read-marking."""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.notifications.models import Notification
from apps.notifications.selectors import inbox, unread_count


class NotificationSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)
    ticket_key = serializers.CharField(source="ticket.key", read_only=True, default=None)
    project_key = serializers.CharField(source="project.key", read_only=True, default=None)

    class Meta:
        model = Notification
        fields = (
            "id",
            "event_type",
            "title",
            "body",
            "actor",
            "actor_name",
            "ticket",
            "ticket_key",
            "project",
            "project_key",
            "payload",
            "is_read",
            "read_at",
            "is_sent",
            "created_at",
        )
        read_only_fields = fields


class NotificationViewSet(viewsets.GenericViewSet):
    """``/api/v1/notifications/`` — the signed-in user's inbox."""

    serializer_class = NotificationSerializer
    filterset_fields = ("event_type", "is_read")
    ordering = ("-created_at",)

    def get_queryset(self):
        # Schema generation inspects the viewset without a real user; filtering by an AnonymousUser
        # raises (it is not a valid UUID). Returning an empty queryset keeps introspection working.
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return inbox(self.request.user)

    @extend_schema(responses={200: NotificationSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        queryset = inbox(request.user, unread_only=request.query_params.get("unread") == "true")
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(NotificationSerializer(page, many=True).data)
        return Response(NotificationSerializer(queryset, many=True).data)

    @extend_schema(responses={200: NotificationSerializer})
    def retrieve(self, request, *args, **kwargs):
        notification = self.get_queryset().filter(pk=kwargs["pk"]).first()
        if notification is None:
            return Response(
                {"error": {"code": "not_found", "detail": _("The requested resource was not found.")}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(NotificationSerializer(notification).data)

    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        """Cheap endpoint for the bell badge (a scalar, not a page of rows)."""
        return Response({"unread": unread_count(request.user)})

    @extend_schema(request=None, responses={200: NotificationSerializer})
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_queryset().filter(pk=pk).first()
        if notification is None:
            return Response(
                {"error": {"code": "not_found", "detail": _("The requested resource was not found.")}},
                status=status.HTTP_404_NOT_FOUND,
            )
        notification.mark_read()
        return Response(NotificationSerializer(notification).data)

    @extend_schema(request=None, responses={200: None})
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = inbox(request.user, unread_only=True).update(is_read=True, read_at=timezone.now())
        return Response({"marked_read": updated})