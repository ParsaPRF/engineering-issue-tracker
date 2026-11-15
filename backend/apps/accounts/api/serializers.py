"""Account API serializers: shape validation only.

Business rules (uniqueness of email, permission to change a role, the last-admin rule) live in
``apps.accounts.services``. Serializers answer "is this payload well-formed?"; services answer
"is this operation allowed?" (ADR-004).
"""

from __future__ import annotations

from django.contrib.auth import password_validation
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.models import SystemRole, User, UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    """Read representation of the profile."""

    class Meta:
        model = UserProfile
        fields = (
            "job_title",
            "phone",
            "timezone",
            "avatar_key",
            "notify_on_assignment",
            "notify_on_comment",
            "notify_on_status_change",
        )
        read_only_fields = fields


class ProjectMembershipSummarySerializer(serializers.Serializer):
    """The caller's own project roles (FR-1.4).

    A plain ``Serializer`` rather than a ``ModelSerializer``: this is a projection of the caller's
    memberships, not a writable resource, and keeping it here avoids importing the projects models
    into the accounts API.
    """

    project_id = serializers.UUIDField()
    project_key = serializers.CharField()
    project_name = serializers.CharField()
    role = serializers.CharField()
    is_active = serializers.BooleanField()


class UserSerializer(serializers.ModelSerializer):
    """Full read representation of a user, including the caller's memberships when relevant."""

    profile = UserProfileSerializer(read_only=True)
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "system_role",
            "is_active",
            "date_joined",
            "profile",
            "memberships",
        )
        read_only_fields = fields

    def get_memberships(self, obj: User) -> list[dict]:
        request = self.context.get("request")
        # Only expose the caller's own memberships: another user's project roles are not this
        # response's business.
        if request is None or getattr(request, "user", None) is None or request.user.pk != obj.pk:
            return []
        return [
            {
                "project_id": membership.project_id,
                "project_key": membership.project.key,
                "project_name": membership.project.name,
                "role": membership.role,
                "is_active": membership.is_active,
            }
            for membership in obj.project_memberships.select_related("project").order_by(
                "project__name"
            )
        ]


class UserSummarySerializer(serializers.ModelSerializer):
    """Directory-safe projection used by member pickers (`PUBLIC_USER_FIELDS`)."""

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "system_role", "is_active")
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    """Input for public registration (FR-1.1)."""

    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_full_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Full name cannot be blank."))
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": _("The passwords do not match.")})

        # Django's validators are the single source of truth for password strength, so the API
        # cannot drift from AUTH_PASSWORD_VALIDATORS.
        password_validation.validate_password(
            attrs["password"],
            user=User(email=attrs["email"], full_name=attrs["full_name"]),
        )
        return attrs


class LoginSerializer(serializers.Serializer):
    """Input for session login.

    Credential *checking* happens in ``services.auth.session_login`` because it needs the request
    to create a session; this serializer only guarantees the fields are present and well-formed.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Writable subset of the profile."""

    class Meta:
        model = UserProfile
        fields = (
            "job_title",
            "phone",
            "timezone",
            "notify_on_assignment",
            "notify_on_comment",
            "notify_on_status_change",
        )

    def validate_timezone(self, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
            raise serializers.ValidationError(_("Unknown time zone.")) from exc
        return value


class MeUpdateSerializer(serializers.Serializer):
    """PATCH /auth/me/ payload: ``full_name`` and/or nested ``profile`` fields."""

    full_name = serializers.CharField(max_length=150, required=False)
    profile = ProfileUpdateSerializer(required=False)

    def validate_full_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Full name cannot be blank."))
        return value


class SystemRoleUpdateSerializer(serializers.Serializer):
    """Admin-only system role change (FR-1.6)."""

    system_role = serializers.ChoiceField(choices=SystemRole.choices)


class PasswordChangeSerializer(serializers.Serializer):
    """Self-service password change."""

    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("The current password is incorrect."))
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["new_password"] != attrs.pop("new_password_confirm"):
            raise serializers.ValidationError(
                {"new_password_confirm": _("The passwords do not match.")}
            )
        password_validation.validate_password(attrs["new_password"], user=self.context["request"].user)
        return attrs
