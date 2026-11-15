"""Ticket API serializers.

Two rules worth noticing:

* ``status`` appears in **no writable serializer**. It is a read-only projection of the lifecycle;
  the only writer is the transition service (ADR-005). The update view additionally rejects a
  ``status`` key with an explicit error instead of ignoring it, so a client that tries cannot
  believe it succeeded.
* derived fields (``is_overdue``, counts) are computed, not stored: a stored "is overdue" flag would
  need a background job to stay true.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.api.serializers import UserSummarySerializer
from apps.tickets.models import Label, Priority, Severity, Ticket, TicketType


class LabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Label
        fields = ("id", "name", "color")
        read_only_fields = fields


class ProjectRefSerializer(serializers.Serializer):
    """Minimal project projection embedded in ticket payloads."""

    id = serializers.UUIDField()
    key = serializers.CharField()
    name = serializers.CharField()


class ComponentRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class TicketListSerializer(serializers.ModelSerializer):
    """Lean representation for tables."""

    project = ProjectRefSerializer(read_only=True)
    component = ComponentRefSerializer(read_only=True)
    reporter = UserSummarySerializer(read_only=True)
    assignee = UserSummarySerializer(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True, required=False)
    attachment_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Ticket
        fields = (
            "id",
            "key",
            "project",
            "component",
            "title",
            "type",
            "status",
            "priority",
            "severity",
            "reporter",
            "assignee",
            "due_date",
            "is_overdue",
            "comment_count",
            "attachment_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TicketSerializer(TicketListSerializer):
    """Full representation, including description and labels, used for detail and mutations."""

    labels = LabelSerializer(many=True, read_only=True)
    resolved_at = serializers.DateTimeField(read_only=True)
    closed_at = serializers.DateTimeField(read_only=True)

    class Meta(TicketListSerializer.Meta):
        fields = TicketListSerializer.Meta.fields + (
            "description",
            "labels",
            "resolved_at",
            "closed_at",
        )
        read_only_fields = fields


class TicketCreateSerializer(serializers.Serializer):
    """``POST /tickets/`` payload. ``status`` is not accepted: new tickets always start at NEW."""

    project = serializers.UUIDField()
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    type = serializers.ChoiceField(choices=TicketType.choices, default=TicketType.BUG)
    priority = serializers.ChoiceField(choices=Priority.choices, default=Priority.MEDIUM)
    severity = serializers.ChoiceField(choices=Severity.choices, default=Severity.MAJOR)
    component = serializers.UUIDField(required=False, allow_null=True)
    assignee = serializers.UUIDField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    labels = serializers.ListField(child=serializers.UUIDField(), required=False)

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title cannot be blank.")
        return value

    def validate_description(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Description cannot be blank.")
        return value


class TicketUpdateSerializer(serializers.Serializer):
    """``PATCH /tickets/<id>/`` payload.

    Every field is optional; the *service* decides which of them this actor may actually change, so
    the error says "you cannot edit this field" rather than "unknown field".
    """

    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False)
    type = serializers.ChoiceField(choices=TicketType.choices, required=False)
    priority = serializers.ChoiceField(choices=Priority.choices, required=False)
    severity = serializers.ChoiceField(choices=Severity.choices, required=False)
    component = serializers.UUIDField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    labels = serializers.ListField(child=serializers.UUIDField(), required=False)

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title cannot be blank.")
        return value

    def validate_description(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Description cannot be blank.")
        return value


class AssignTicketSerializer(serializers.Serializer):
    """``POST /tickets/<id>/assign/`` payload. ``assignee: null`` unassigns."""

    assignee = serializers.UUIDField(required=False, allow_null=True, default=None)


class TicketStatusChoiceSerializer(serializers.Serializer):
    """Read-only helper for docs: the status enumeration."""

    value = serializers.CharField()
    label = serializers.CharField()


class TicketChoicesSerializer(serializers.Serializer):
    """``GET /tickets/choices/`` — enumerations for building forms without hard-coding them."""

    statuses = TicketStatusChoiceSerializer(many=True)
    types = TicketStatusChoiceSerializer(many=True)
    priorities = TicketStatusChoiceSerializer(many=True)
    severities = TicketStatusChoiceSerializer(many=True)