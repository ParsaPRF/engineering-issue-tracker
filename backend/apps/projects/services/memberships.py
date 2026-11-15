"""Membership services.

Membership is the pivot of authorisation, so these functions carry the rules that keep a project
manageable:

* the owner is always an active ``MANAGER``;
* a project always has at least one active ``MANAGER`` (otherwise nobody could administer it);
* deactivated users cannot be added (they cannot log in, so the membership would be a lie);
* membership is deactivated, never deleted, so "who was on this project then?" stays answerable.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q

from apps.audit.actions import AuditAction
from apps.audit.services import record as audit_record
from apps.notifications.services import notify_membership_added
from apps.projects.models import Project, ProjectMembership, ProjectRole
from apps.projects.permissions import can_manage_members
from common.exceptions import AccessDenied, InvariantViolation


def _validate_role(role: str) -> str:
    if not ProjectRole.has_value(role):
        raise InvariantViolation(
            "Unknown project role.",
            code="invalid_role",
            fields={"role": [f"'{role}' is not a valid project role."]},
        )
    return role


def _active_managers(project: Project):
    return ProjectMembership.objects.filter(project=project, role=ProjectRole.MANAGER, is_active=True)


def _assert_not_last_manager(project: Project, membership: ProjectMembership) -> None:
    """Guard the "a project always has a manager" invariant."""
    if membership.role != ProjectRole.MANAGER or not membership.is_active:
        return
    others = _active_managers(project).exclude(pk=membership.pk).exists()
    if not others:
        raise InvariantViolation(
            "A project must keep at least one active manager; add another manager first.",
            code="last_manager",
        )


@transaction.atomic
def add_member(*, actor, project: Project, user, role: str, request=None) -> tuple[ProjectMembership, bool]:
    """Add a member, or reactivate/re-role an existing membership (FR-2.5).

    Returns ``(membership, created)`` so the caller can distinguish "added" from "updated" without a
    second query, and so audit/notification wording can be accurate.
    """
    if not can_manage_members(actor, project):
        raise AccessDenied("You cannot manage the members of this project.")
    _validate_role(role)

    if not user.is_active:
        raise InvariantViolation(
            "Deactivated users cannot be added to a project.",
            code="inactive_user",
            fields={"user": ["This user is deactivated."]},
        )

    membership, created = ProjectMembership.objects.get_or_create(
        project=project,
        user=user,
        defaults={"role": role, "is_active": True},
    )

    if created:
        audit_record(
            action=AuditAction.MEMBERSHIP_ADDED,
            actor=actor,
            obj=membership,
            project=project,
            metadata={"user_id": str(user.pk), "email": user.email, "role": role},
            request=request,
        )
        notify_membership_added(project=project, user=user, actor=actor)
        return membership, True

    if membership.is_active and membership.role == role:
        return membership, False

    previous_role = membership.role
    was_active = membership.is_active

    # Reactivating or demoting the last manager would leave the project unmanageable.
    if was_active and membership.role == ProjectRole.MANAGER and role != ProjectRole.MANAGER:
        _assert_not_last_manager(project, membership)

    membership.role = role
    membership.is_active = True
    membership.save(update_fields=["role", "is_active", "updated_at"])

    audit_record(
        action=AuditAction.MEMBERSHIP_REACTIVATED if not was_active else AuditAction.MEMBERSHIP_ROLE_CHANGED,
        actor=actor,
        obj=membership,
        project=project,
        metadata={"user_id": str(user.pk), "from": previous_role, "to": role},
        request=request,
    )
    return membership, False


@transaction.atomic
def change_member_role(*, actor, project: Project, membership: ProjectMembership, role: str, request=None) -> ProjectMembership:
    """Change one member's project role."""
    if not can_manage_members(actor, project):
        raise AccessDenied("You cannot manage the members of this project.")
    _validate_role(role)

    if project.owner_id == membership.user_id and role != ProjectRole.MANAGER:
        raise InvariantViolation(
            "The project owner must keep the MANAGER role; transfer ownership first.",
            code="owner_must_be_manager",
        )
    if membership.role == role:
        return membership

    if membership.role == ProjectRole.MANAGER and role != ProjectRole.MANAGER:
        _assert_not_last_manager(project, membership)

    previous = membership.role
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])

    audit_record(
        action=AuditAction.MEMBERSHIP_ROLE_CHANGED,
        actor=actor,
        obj=membership,
        project=project,
        metadata={"user_id": str(membership.user_id), "from": previous, "to": role},
        request=request,
    )
    return membership


@transaction.atomic
def remove_member(*, actor, project: Project, membership: ProjectMembership, request=None) -> ProjectMembership:
    """Remove a member by deactivating the membership row (history is preserved)."""
    if not can_manage_members(actor, project):
        raise AccessDenied("You cannot manage the members of this project.")

    if project.owner_id == membership.user_id:
        raise InvariantViolation(
            "The project owner cannot be removed from the project.",
            code="owner_cannot_be_removed",
        )
    if not membership.is_active:
        raise InvariantViolation("This membership is already inactive.", code="already_inactive")

    _assert_not_last_manager(project, membership)

    membership.is_active = False
    membership.save(update_fields=["is_active", "updated_at"])

    # Keep the workload coherent: a removed member cannot stay the assignee of open tickets, or the
    # ticket would sit with somebody who no longer has access to it.
    from apps.tickets.models import OPEN_STATUSES, Ticket  # local import avoids an import cycle

    Ticket.objects.filter(project=project, assignee=membership.user, status__in=OPEN_STATUSES).update(
        assignee=None
    )

    audit_record(
        action=AuditAction.MEMBERSHIP_REMOVED,
        actor=actor,
        obj=membership,
        project=project,
        metadata={"user_id": str(membership.user_id), "role": membership.role},
        request=request,
    )
    return membership


def eligible_managers_query(project: Project):
    """Active managers of a project — used when computing notification recipients.

    Lives here (not in the API layer) because both the notification and reporting modules need the
    same definition of "the people responsible for this project".
    """
    return (
        ProjectMembership.objects.filter(
            Q(project=project) & Q(role=ProjectRole.MANAGER) & Q(is_active=True)
        )
        .select_related("user")
    )
