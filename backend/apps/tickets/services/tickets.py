"""Ticket services: create, update, assign.

Position in the architecture: this module owns the *ticket's own* business rules. It deliberately
does **not** change status (that is ``apps.workflows``) and does not write comments or attachments
(their own modules). Each function therefore stays short and its permission story stays obvious.

The creation path is the most interesting one: the key is allocated by
``apps.tickets.services.keys`` under a lock, history is opened by ``apps.workflows``, and an audit
event is written — all inside one transaction, so a half-created ticket cannot exist.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from django.db import transaction

from apps.audit.actions import AuditAction
from apps.audit.services import record as audit_record
from apps.notifications.services import notify_ticket_assigned, notify_ticket_created
from apps.projects.models import Component, Project, ProjectRole
from apps.projects.permissions import (
    can_assign_ticket,
    can_create_ticket,
    editable_ticket_fields,
    has_project_role,
    is_eligible_assignee,
)
from apps.tickets.models import Priority, Severity, Ticket, TicketLabel, TicketStatus, TicketType
from apps.tickets.services.keys import create_with_allocated_key
from apps.workflows.services import record_initial_status
from common.exceptions import AccessDenied, InvariantViolation

#: Fields a client may send when creating a ticket. ``status`` is absent by design (ADR-005).
TICKET_CREATE_FIELDS = (
    "title",
    "description",
    "type",
    "priority",
    "severity",
    "component",
    "assignee",
    "due_date",
    "labels",
)


def _assert_archived_allows_work(project: Project) -> None:
    if project.is_archived:
        raise InvariantViolation(
            "This project is archived and no longer accepts new tickets.",
            code="project_archived",
        )


def _validate_component(project: Project, component: Component | None) -> None:
    if component is None:
        return
    if component.project_id != project.id:
        raise InvariantViolation(
            "The component must belong to the ticket's project.",
            code="invalid_component",
            fields={"component": ["This component belongs to another project."]},
        )
    if not component.is_active:
        raise InvariantViolation(
            "This component is inactive.",
            code="inactive_component",
            fields={"component": ["This component is no longer offered for new tickets."]},
        )


def _validate_assignee(project: Project, assignee, *, actor) -> None:
    """An assignee must be able to do the work, and only a manager may assign somebody else."""
    if assignee is None:
        return
    if not is_eligible_assignee(assignee, project):
        raise InvariantViolation(
            "The assignee must be an active engineer or manager of this project.",
            code="ineligible_assignee",
            fields={"assignee": ["This user cannot be assigned work in this project."]},
        )
    if assignee.id != actor.id and not has_project_role(actor, project, {ProjectRole.MANAGER}):
        raise AccessDenied("Only project managers can assign work to other people.")


def _apply_labels(ticket: Ticket, labels) -> None:
    """Replace the ticket's labels with ``labels`` (validated to belong to the project)."""
    if labels is None:
        return
    label_ids = [getattr(label, "id", label) for label in labels]
    valid_ids = set(
        ticket.project.labels.filter(id__in=label_ids).values_list("id", flat=True)
    )
    invalid = [str(label_id) for label_id in label_ids if label_id not in valid_ids]
    if invalid:
        raise InvariantViolation(
            "One or more labels do not belong to the ticket's project.",
            code="invalid_labels",
            fields={"labels": [f"Unknown label(s): {', '.join(invalid)}"]},
        )
    TicketLabel.objects.filter(ticket=ticket).delete()
    TicketLabel.objects.bulk_create(
        [TicketLabel(ticket=ticket, label_id=label_id) for label_id in label_ids],
        ignore_conflicts=True,
    )


@transaction.atomic
def create_ticket(
    *,
    actor,
    project: Project,
    title: str,
    description: str,
    type: str = TicketType.BUG,
    priority: str = Priority.MEDIUM,
    severity: str = Severity.MAJOR,
    component: Component | None = None,
    assignee=None,
    due_date: date | None = None,
    labels=None,
    request=None,
) -> Ticket:
    """Create a ticket, allocating a unique key atomically (FR-3.1 … FR-3.6)."""
    if project.is_archived:
        _assert_archived_allows_work(project)
    if not can_create_ticket(actor, project):
        raise AccessDenied("You must be a member of this project to report a ticket.")

    _validate_component(project, component)
    _validate_assignee(project, assignee, actor=actor)

    def build(key: str) -> Ticket:
        ticket = Ticket(
            key=key,
            project=project,
            component=component,
            title=title.strip(),
            description=description.strip(),
            type=type,
            priority=priority,
            severity=severity,
            reporter=actor,
            assignee=assignee,
            due_date=due_date,
            status=TicketStatus.NEW,
        )
        ticket.full_clean(exclude=["reporter", "key"])
        ticket.save()
        return ticket

    ticket = create_with_allocated_key(project=project, build=build)

    _apply_labels(ticket, labels)

    # The timeline and the audit trail open together with the ticket, in this transaction.
    record_initial_status(ticket=ticket, actor=actor)
    audit_record(
        action=AuditAction.TICKET_CREATED,
        actor=actor,
        obj=ticket,
        project=project,
        ticket=ticket,
        metadata={"key": ticket.key, "type": ticket.type, "priority": ticket.priority},
        request=request,
    )
    # Notification rows are created inside the transaction (so they are consistent with the ticket)
    # but their *delivery* is asynchronous (ADR-009).
    notify_ticket_created(ticket=ticket, actor=actor)
    if ticket.assignee_id:
        notify_ticket_assigned(ticket=ticket, actor=actor)
    return ticket


@transaction.atomic
def update_ticket(*, actor, ticket: Ticket, data: Mapping[str, Any], request=None) -> Ticket:
    """Update the fields this actor is allowed to change (FR-3.9).

    The allowed field set comes from the permission kernel, so "what may a reporter change?" is
    answered in one place instead of being re-derived here.
    """
    allowed = editable_ticket_fields(actor, ticket)
    if not allowed:
        raise AccessDenied("You cannot edit this ticket.")

    if "assignee" in data:
        # Assignment has its own endpoint, with its own rules (notification, eligibility, audit
        # wording). Silently allowing it here would create a second, weaker path.
        raise InvariantViolation(
            "Use the assignment endpoint to change the assignee.",
            code="use_assignment_endpoint",
            fields={"assignee": ["Change the assignee through the assign endpoint."]},
        )
    if "status" in data:
        raise InvariantViolation(
            "Ticket status changes go through the transition endpoint.",
            code="use_transition_endpoint",
            fields={"status": ["Use POST /tickets/<id>/transitions/ to change the status."]},
        )

    requested = {field for field in data if field in TICKET_FIELDS}
    forbidden = requested - allowed
    if forbidden:
        raise InvariantViolation(
            "You cannot change these fields on this ticket.",
            code="field_not_editable",
            fields={field: ["You cannot edit this field."] for field in sorted(forbidden)},
        )

    changed: dict[str, Any] = {}

    if "component" in data:
        _validate_component(ticket.project, data["component"])
    if "title" in data and not str(data["title"]).strip():
        raise InvariantViolation(
            "Title cannot be blank.", code="validation_error", fields={"title": ["This field is required."]}
        )
    if "description" in data and not str(data["description"]).strip():
        raise InvariantViolation(
            "Description cannot be blank.",
            code="validation_error",
            fields={"description": ["This field is required."]},
        )

    for field in TICKET_FIELDS:
        if field not in data:
            continue
        new_value = data[field]
        if isinstance(new_value, str):
            new_value = new_value.strip()
        current = getattr(ticket, field)
        if current != new_value:
            changed[field] = {"from": str(current), "to": str(new_value)}
            setattr(ticket, field, new_value)

    if "labels" in data:
        _apply_labels(ticket, data["labels"])

    if not changed and "labels" not in data:
        return ticket

    ticket.full_clean(exclude=["key", "status", "reporter", "project", "resolved_at", "closed_at"])
    ticket.save()

    audit_record(
        action=AuditAction.TICKET_UPDATED,
        actor=actor,
        obj=ticket,
        project=ticket.project,
        ticket=ticket,
        metadata={"changed": changed, "labels_updated": "labels" in data},
        request=request,
    )
    return ticket


#: Fields a client may attempt to change through the update endpoint. Immutable identity fields
#: (``key``, ``project``, ``reporter``) and derived ones (``status``, ``resolved_at``) are excluded.
TICKET_FIELDS = ("title", "description", "type", "priority", "severity", "component", "due_date")


@transaction.atomic
def assign_ticket(*, actor, ticket: Ticket, assignee, request=None) -> Ticket:
    """Assign, reassign or unassign a ticket (FR-4.1 … FR-4.3)."""
    if assignee is not None and assignee.id == ticket.assignee_id:
        return ticket

    if assignee is None:
        if ticket.assignee_id is None:
            return ticket
        if not has_project_role(actor, ticket.project, {ProjectRole.MANAGER}):
            raise AccessDenied("Only project managers can unassign a ticket.")
        action = AuditAction.TICKET_UNASSIGNED
    else:
        if not can_assign_ticket(actor, ticket):
            raise AccessDenied(
                "Only project managers can assign this ticket; engineers may claim unassigned tickets."
            )
        _validate_assignee(ticket.project, assignee, actor=actor)
        action = AuditAction.TICKET_ASSIGNED if ticket.assignee_id is None else AuditAction.TICKET_REASSIGNED

    previous_assignee_id = ticket.assignee_id
    ticket.assignee = assignee
    ticket.save(update_fields=["assignee", "updated_at"])

    audit_record(
        action=action,
        actor=actor,
        obj=ticket,
        project=ticket.project,
        ticket=ticket,
        metadata={
            "from": str(previous_assignee_id) if previous_assignee_id else None,
            "to": str(assignee.id) if assignee else None,
        },
        request=request,
    )
    if assignee is not None:
        notify_ticket_assigned(ticket=ticket, actor=actor, previous_assignee_id=previous_assignee_id)
    return ticket


@transaction.atomic
def set_ticket_labels(*, actor, ticket: Ticket, labels, request=None) -> Ticket:
    """Replace a ticket's labels as an explicit operation (audited on its own)."""
    if not editable_ticket_fields(actor, ticket):
        raise AccessDenied("You cannot edit this ticket.")

    _apply_labels(ticket, labels)
    audit_record(
        action=AuditAction.TICKET_LABELS_CHANGED,
        actor=actor,
        obj=ticket,
        project=ticket.project,
        ticket=ticket,
        metadata={"labels": [str(getattr(label, "id", label)) for label in (labels or [])]},
        request=request,
    )
    return ticket