"""Project API serializers.

Read serializers expose computed numbers (``member_count`` and friends) that come from annotations
in the selector; they use ``SerializerMethodField`` so the same serializer also works for a detail
object that was not annotated, instead of raising ``AttributeError``.

Write serializers contain **only** shape rules. Everything decision-shaped — unique key, owner
becomes manager, last-manager protection — is enforced by ``apps.projects.services``.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.api.serializers import UserSummarySerializer
from apps.projects.models import Component, Project, ProjectMembership, ProjectRole, ProjectStatus
from apps.projects.models.project import project_key_validator


class ProjectMembershipSerializer(serializers.ModelSerializer):
    """Read representation of a membership row."""

    user = UserSummarySerializer(read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = ProjectMembership
        fields = ("id", "user", "user_name", "user_email", "role", "is_active", "joined_at", "created_at")
        read_only_fields = fields


class ProjectSerializer(serializers.ModelSerializer):
    """Read representation of a project."""

    owner = UserSummarySerializer(read_only=True)
    member_count = serializers.SerializerMethodField()
    ticket_count = serializers.SerializerMethodField()
    open_ticket_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            "id",
            "key",
            "name",
            "description",
            "status",
            "owner",
            "archived_at",
            "created_at",
            "updated_at",
            "member_count",
            "ticket_count",
            "open_ticket_count",
        )
        read_only_fields = fields

    def get_member_count(self, obj) -> int | None:
        count = getattr(obj, "member_count", None)
        if count is not None:
            return count
        return obj.memberships.filter(is_active=True).count()

    def get_ticket_count(self, obj) -> int | None:
        count = getattr(obj, "ticket_count", None)
        return count if count is not None else obj.tickets.count()

    def get_open_ticket_count(self, obj) -> int | None:
        count = getattr(obj, "open_ticket_count", None)
        if count is not None:
            return count
        from apps.tickets.models import OPEN_STATUSES

        return obj.tickets.filter(status__in=list(OPEN_STATUSES)).count()


class ProjectCreateSerializer(serializers.Serializer):
    """``POST /projects/`` payload.

    Note the (deliberate) absence of ``validators=[project_key_validator]`` on the field: DRF runs
    field validators *before* ``validate_key``, so a validator here would reject ``"eng"`` before the
    method had a chance to upper-case it. Normalisation first, then validation — the ordering bug
    this comment exists to prevent from coming back.
    """

    key = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_key(self, value: str) -> str:
        value = (value or "").strip().upper()
        try:
            project_key_validator(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Project name cannot be blank.")
        return value


class ProjectUpdateSerializer(serializers.Serializer):
    """``PATCH /projects/<id>/`` payload. ``key`` is immutable: it is the ticket-key prefix."""

    name = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Project name cannot be blank.")
        return value


class MembershipCreateSerializer(serializers.Serializer):
    """``POST /projects/<id>/members/`` payload."""

    user = serializers.UUIDField()
    role = serializers.ChoiceField(choices=ProjectRole.choices, default=ProjectRole.REPORTER)


class MembershipRoleUpdateSerializer(serializers.Serializer):
    """``PATCH /projects/<id>/members/<membership_id>/`` payload."""

    role = serializers.ChoiceField(choices=ProjectRole.choices)


class ComponentSerializer(serializers.ModelSerializer):
    """Read representation of a component."""

    lead = UserSummarySerializer(read_only=True)

    class Meta:
        model = Component
        fields = ("id", "project", "name", "description", "lead", "is_active", "created_at", "updated_at")
        read_only_fields = fields


class ComponentCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    lead = serializers.UUIDField(required=False, allow_null=True)

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Component name cannot be blank.")
        return value


class ComponentUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    lead = serializers.UUIDField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)


class ProjectStatusUpdateSerializer(serializers.Serializer):
    """Payload for archiving or restoring a project."""

    status = serializers.ChoiceField(choices=ProjectStatus.choices)
