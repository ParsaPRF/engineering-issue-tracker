"""Project services: the only writers of Project, ProjectMembership and Component.

Every function follows the same contract:

1. check permission **inside** the service (the API check is not the guarantee, ADR-012),
2. validate business rules and raise a `DomainError` subclass on failure,
3. write inside a transaction,
4. record an audit event in the same transaction — so an operation that rolls back leaves no audit
   trace claiming it happened.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.db import transaction

from apps.audit.actions import AuditAction
from apps.audit.services import record as audit_record
from apps.projects.models import Project, ProjectMembership, ProjectRole, ProjectStatus
from apps.projects.permissions import can_create_project, can_manage_project
from common.exceptions import AccessDenied, InvariantViolation

PROJECT_EDITABLE_FIELDS = frozenset({"name", "description"})


@transaction.atomic
def create_project(*, actor, key: str, name: str, description: str = "", request=None) -> Project:
    """Create a project and make the creator its owner and first manager (FR-2.1).

    The `TicketKeySequence` row is intentionally **not** created here: the counter is the tickets
    module's concern, and creating it lazily in ``tickets.services.keys`` keeps this module free of
    cross-module coupling ("get_or_create" there is race-safe).
    """
    if not can_create_project(actor):
        raise AccessDenied("Only administrators and project managers can create projects.")

    normalised_key = (key or "").strip().upper()
    if Project.objects.filter(key__iexact=normalised_key).exists():
        raise InvariantViolation(
            "A project with this key already exists.",
            code="duplicate_project_key",
            fields={"key": ["A project with this key already exists."]},
        )

    project = Project(key=normalised_key, name=(name or "").strip(), description=description or "", owner=actor)
    project.full_clean(exclude=["owner"])
    project.save()

    # "The project owner always has an active MANAGER membership" is an invariant of the schema
    # (ProjectMembership.clean enforces the role half of it); this is where it is established.
    ProjectMembership.objects.create(project=project, user=actor, role=ProjectRole.MANAGER)

    audit_record(
        action=AuditAction.PROJECT_CREATED,
        actor=actor,
        obj=project,
        project=project,
        metadata={"key": project.key, "name": project.name},
        request=request,
    )
    return project


@transaction.atomic
def update_project(*, actor, project: Project, data: Mapping[str, Any], request=None) -> Project:
    """Update mutable project fields (FR-2.3)."""
    if not can_manage_project(actor, project):
        raise AccessDenied("You cannot edit this project.")

    changed: dict[str, Any] = {}
    for field, value in data.items():
        if field not in PROJECT_EDITABLE_FIELDS:
            continue
        if isinstance(value, str):
            value = value.strip()
        if getattr(project, field) != value:
            changed[field] = {"from": getattr(project, field), "to": value}
            setattr(project, field, value)

    if not changed:
        return project

    project.full_clean(exclude=["owner", "key"])
    project.save()

    audit_record(
        action=AuditAction.PROJECT_UPDATED,
        actor=actor,
        obj=project,
        project=project,
        metadata={"changed": changed},
        request=request,
    )
    return project


@transaction.atomic
def archive_project(*, actor, project: Project, request=None) -> Project:
    """Archive a project (FR-2.4). Deletion is not part of the lifecycle."""
    if not can_manage_project(actor, project):
        raise AccessDenied("You cannot archive this project.")
    if project.status == ProjectStatus.ARCHIVED:
        raise InvariantViolation("This project is already archived.", code="already_archived")

    project.archive()
    audit_record(
        action=AuditAction.PROJECT_ARCHIVED,
        actor=actor,
        obj=project,
        project=project,
        request=request,
    )
    return project


@transaction.atomic
def restore_project(*, actor, project: Project, request=None) -> Project:
    """Bring an archived project back to active."""
    if not can_manage_project(actor, project):
        raise AccessDenied("You cannot restore this project.")
    if project.status == ProjectStatus.ACTIVE:
        raise InvariantViolation("This project is not archived.", code="not_archived")

    project.restore()
    audit_record(
        action=AuditAction.PROJECT_RESTORED,
        actor=actor,
        obj=project,
        project=project,
        request=request,
    )
    return project
