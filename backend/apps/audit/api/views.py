"""Audit API: strictly read-only.

There is intentionally no create, update or delete endpoint. Events are produced by services as a
side effect of real operations; an API that could write audit rows would be an API that can forge
history (FR-8.3).
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets

from apps.audit.models import AuditEvent
from apps.audit.selectors import list_events
from common.permissions import IsAdmin


class AuditEventSerializer(serializers.ModelSerializer):
    """Read-only projection of an audit event."""

    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)
    project_key = serializers.CharField(source="project.key", read_only=True, default=None)
    ticket_key = serializers.CharField(source="ticket.key", read_only=True, default=None)

    class Meta:
        model = AuditEvent
        fields = (
            "id",
            "action",
            "actor",
            "actor_email",
            "actor_name",
            "object_type",
            "object_id",
            "project",
            "project_key",
            "ticket",
            "ticket_key",
            "metadata",
            "ip_address",
            "user_agent",
            "created_at",
        )
        read_only_fields = fields


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    """``GET /api/v1/audit/`` and ``GET /api/v1/audit/<id>/``.

    Only administrators may use the full audit API; project members see their project's activity
    through the reports endpoints instead.
    """

    serializer_class = AuditEventSerializer
    # Business role, not Django's ``is_staff``: the audit trail is part of the product's
    # authorisation model, and an operator whose role is ADMIN but who has no Django-admin account
    # still needs to read it.
    permission_classes = [IsAdmin]
    filterset_fields = ("action", "object_type", "project", "ticket", "actor")
    ordering_fields = ("created_at", "action")
    ordering = ("-created_at",)

    @extend_schema(description=_("List audit events. Administrator only."))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        return list_events(
            self.request.user,
            project_id=self.request.query_params.get("project"),
            ticket_id=self.request.query_params.get("ticket"),
        )
