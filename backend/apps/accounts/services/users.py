"""Account services: every write to users and profiles goes through here.

Why services rather than serializer ``create``/``update`` methods: the same operations are invoked
from the API, from the Django admin, from management commands (``seed_demo``) and from tests. A
service is the only place that can also enforce permissions, write the audit event and keep the
"one active manager per project" style invariants — none of which a serializer should know about
(ADR-004).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import SystemRole, User, UserProfile
from apps.audit.actions import AuditAction
from apps.audit.services import record as audit_record
from common.exceptions import AccessDenied, InvariantViolation

PROFILE_EDITABLE_FIELDS = frozenset(
    {
        "job_title",
        "phone",
        "timezone",
        "notify_on_assignment",
        "notify_on_comment",
        "notify_on_status_change",
        "avatar_key",
    }
)


# ---------------------------------------------------------------------------
# Registration and profile
# ---------------------------------------------------------------------------
def ensure_profile(user: User) -> UserProfile:
    """Return the user's profile, creating it if the account predates it.

    ``UserManager`` creates the profile at registration time, but rows can also appear through data
    imports, fixtures or a direct ``User.objects.create()``. A read path that raises
    ``RelatedObjectDoesNotExist`` in those cases would turn a data-quality problem into a 500, so
    the API resolves profiles through this helper.
    """
    profile, _created = UserProfile.objects.get_or_create(user=user)
    return profile


@transaction.atomic
def register_user(
    *,
    email: str,
    password: str,
    full_name: str,
    request=None,
    system_role: str = SystemRole.REPORTER,
) -> User:
    """Create an account through the public registration path.

    ``system_role`` is a parameter (not taken from user input) so that tests and the seed command
    can create users of any role, while the API always registers the least-privileged role. It can
    only be raised through :func:`change_system_role`, which is Admin-only and audited.
    """
    if not getattr(settings, "ALLOW_SELF_REGISTRATION", True) and request is not None:
        raise InvariantViolation(
            "Self-registration is disabled on this installation.",
            code="registration_disabled",
            status_code=403,
        )

    normalised_email = (email or "").strip().lower()
    if User.objects.filter(email__iexact=normalised_email).exists():
        raise InvariantViolation(
            "An account with this email address already exists.",
            code="email_taken",
            fields={"email": ["An account with this email address already exists."]},
        )

    user = User.objects.create_user(
        email=normalised_email,
        password=password,
        full_name=full_name.strip(),
        system_role=system_role,
    )

    audit_record(
        action=AuditAction.USER_REGISTERED,
        actor=user,
        obj=user,
        metadata={"email": user.email, "system_role": user.system_role},
        request=request,
    )
    return user


@transaction.atomic
def update_profile(*, actor: User, profile: UserProfile, data: Mapping[str, Any], request=None) -> UserProfile:
    """Update the presentation/preference fields of a profile.

    Only the owner or an Admin may act; ``user`` itself (and therefore the email) is not in
    ``PROFILE_EDITABLE_FIELDS``, so an attacker cannot move an account's identity.
    """
    if actor.id != profile.user_id and actor.system_role != SystemRole.ADMIN:
        raise AccessDenied("You can only edit your own profile.")

    changed: dict[str, Any] = {}
    for field, value in data.items():
        if field not in PROFILE_EDITABLE_FIELDS:
            continue
        current = getattr(profile, field)
        if current != value:
            changed[field] = {"from": current, "to": value}
            setattr(profile, field, value)

    if not changed:
        return profile

    profile.full_clean(exclude=[f.name for f in profile._meta.fields if f.name not in PROFILE_EDITABLE_FIELDS])
    profile.save()

    audit_record(
        action=AuditAction.USER_PROFILE_UPDATED,
        actor=actor,
        obj=profile.user,
        metadata={"changed": list(changed.keys())},
        request=request,
    )
    return profile


# ---------------------------------------------------------------------------
# Activation, role changes
# ---------------------------------------------------------------------------
def invalidate_user_sessions(user: User) -> int:
    """Delete the user's server-side sessions so deactivation takes effect immediately.

    Why not a token blacklist: with session authentication the session *is* the credential, so
    removing the row revokes it everywhere at once (ADR-003). The scan is linear in the number of
    live sessions, which is acceptable at this scale; a cache-backed session store or a
    ``session_version`` column on the user is the scalable alternative.
    """
    deleted = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        data = session.get_decoded()
        if str(data.get("_auth_user_id")) == str(user.pk):
            session.delete()
            deleted += 1
    return deleted


@transaction.atomic
def set_user_active(*, actor: User, user: User, is_active: bool, request=None) -> User:
    """Activate or deactivate an account (Admin only)."""
    if actor.system_role != SystemRole.ADMIN:
        raise AccessDenied("Only administrators can change account status.")
    if actor.id == user.id and not is_active:
        raise InvariantViolation(
            "You cannot deactivate your own account.",
            code="self_deactivation",
        )

    if user.is_active == is_active:
        return user

    user.is_active = is_active
    user.save(update_fields=["is_active", "updated_at"])

    if not is_active:
        invalidate_user_sessions(user)

    audit_record(
        action=AuditAction.USER_ACTIVATED if is_active else AuditAction.USER_DEACTIVATED,
        actor=actor,
        obj=user,
        metadata={"is_active": is_active},
        request=request,
    )
    return user


@transaction.atomic
def change_system_role(*, actor: User, user: User, system_role: str, request=None) -> User:
    """Change a user's global role (Admin only).

    Refuses to remove the last administrator: an installation with no Admin cannot be recovered
    through the API, which turns a routine action into an outage.
    """
    if actor.system_role != SystemRole.ADMIN:
        raise AccessDenied("Only administrators can change system roles.")
    if not SystemRole.has_value(system_role):
        raise InvariantViolation(
            "Unknown system role.",
            code="invalid_role",
            fields={"system_role": [f"'{system_role}' is not a valid role."]},
        )
    if user.system_role == system_role:
        return user

    if user.system_role == SystemRole.ADMIN and system_role != SystemRole.ADMIN:
        remaining_admins = (
            User.objects.filter(system_role=SystemRole.ADMIN, is_active=True)
            .exclude(pk=user.pk)
            .count()
        )
        if remaining_admins == 0:
            raise InvariantViolation(
                "The last administrator cannot be demoted; promote another administrator first.",
                code="last_admin",
            )

    previous = user.system_role
    user.system_role = system_role
    # Keep Django-admin access consistent with the business role: only Admins get it.
    user.is_staff = system_role == SystemRole.ADMIN or user.is_superuser
    user.save(update_fields=["system_role", "is_staff", "updated_at"])

    audit_record(
        action=AuditAction.USER_ROLE_CHANGED,
        actor=actor,
        obj=user,
        metadata={"from": previous, "to": system_role},
        request=request,
    )
    return user
