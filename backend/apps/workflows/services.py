"""The only operation that may change ``Ticket.status`` (ADR-005, FR-5.1 … FR-5.7).

The sequence inside :func:`transition_ticket` is the important part:

1. **Lock the ticket row** (``select_for_update``) so two operators cannot both apply a move computed
   from the same ``from_status``. Without the lock, the second request would validate against stale
   state and could skip a status (e.g. two simultaneous ``IN_REVIEW → RESOLVED``) or resurrect a
   closed ticket.
2. **Look the move up in the state machine.** Not in the table → ``invalid_transition`` (400).
3. **Check the actor's project role** via the permission kernel. Wrong role → 403, which the UI can
   distinguish from "impossible move".
4. **Check guards**: a required comment, a required assignee.
5. **Apply** the status and the derived timestamps.
6. **Append the history row** and **record the audit event**. Both happen in the same transaction as
   the status change, so history can never disagree with ``Ticket.status``.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.audit.actions import AuditAction
from apps.audit.services import record as audit_record
from apps.notifications.services import notify_status_changed
from apps.projects.models import ProjectRole
from apps.projects.permissions import can_transition_ticket
from apps.tickets.models import TicketStatus
from apps.workflows import state_machine
from apps.workflows.models import TicketStatusHistory
from common.exceptions import AccessDenied, InvariantViolation


def record_initial_status(*, ticket, actor) -> TicketStatusHistory:
    """Write the creation entry of the timeline (``from_status = null``).

    Called by ``tickets.services.create_ticket`` inside the same transaction as the insert, so a
    ticket can never exist without a first history row.
    """
    return TicketStatusHistory.objects.create(
        ticket=ticket,
        from_status=None,
        to_status=ticket.status,
        changed_by=actor,
        comment="Ticket created.",
    )


def allowed_transitions_for(*, ticket, actor) -> list[dict]:
    """What ``actor`` could do to ``ticket`` right now (FR-5.8).

    Returns move descriptions with ``blocked_by`` explaining unsatisfied preconditions. The frontend
    builds its buttons from this, so the UI cannot offer a move the backend would reject — and when a
    move is unavailable it can say *why* instead of silently hiding it.
    """
    available: list[dict] = []
    for rule in state_machine.rules_from(ticket.status):
        permitted = can_transition_ticket(
            actor,
            ticket,
            allowed_project_roles=rule.allowed_project_roles,
            allow_assignee=rule.allow_assignee,
        )
        if not permitted:
            continue
        payload = state_machine.describe(rule)
        failures = state_machine.guard_failures(rule, ticket)
        payload["blocked_by"] = failures
        payload["available"] = not failures
        available.append(payload)
    return available


@transaction.atomic
def transition_ticket(
    *,
    ticket,
    to_status: str,
    actor,
    comment: str = "",
    request=None,
) -> TicketStatusHistory:
    """Move ``ticket`` to ``to_status``, recording history and an audit event.

    Raises:
        InvalidTransition: the move is not in the table, or is a no-op.
        AccessDenied: the actor's project role does not permit the move.
        InvariantViolation: a guard failed (missing comment or assignee).
    """
    from apps.tickets.models import Ticket  # local import keeps the module graph acyclic

    if not TicketStatus.has_value(to_status):
        raise InvariantViolation(
            "Unknown ticket status.",
            code="invalid_status",
            fields={"to_status": [f"'{to_status}' is not a valid ticket status."]},
        )

    # Re-read under a row lock: the caller's instance may be stale.
    #
    # ``select_related`` must NOT include a nullable relation here. ``assignee`` is nullable, so
    # joining it produces a LEFT OUTER JOIN, and PostgreSQL rejects ``FOR UPDATE`` on the nullable
    # side of an outer join:
    #     NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
    # SQLite silently ignored the whole clause, so the SQLite-only test run could not catch it —
    # this was a real production bug (every transition would have been a 500) until PostgreSQL ran
    # the suite. ``project`` and ``reporter`` are non-nullable, so joining them keeps INNER joins and
    # one query; ``assignee`` is loaded lazily only if something actually reads the object (the
    # permission and guard checks use ``assignee_id`` and never trigger that query).
    locked = (
        Ticket.objects.select_for_update()
        .select_related("project", "reporter")
        .get(pk=ticket.pk)
    )

    if state_machine.is_noop(locked.status, to_status):
        raise state_machine.InvalidTransition(
            f"The ticket is already {TicketStatus(to_status).label}.",
            code="noop_transition",
        )

    rule = state_machine.get_rule(locked.status, to_status)
    if rule is None:
        raise state_machine.InvalidTransition(
            f"Cannot move a ticket from {TicketStatus(locked.status).label} to "
            f"{TicketStatus(to_status).label}.",
            code="invalid_transition",
        )

    permitted = can_transition_ticket(
        actor,
        locked,
        allowed_project_roles=rule.allowed_project_roles,
        allow_assignee=rule.allow_assignee,
    )
    if not permitted:
        raise AccessDenied(
            "Your project role does not allow this status change.",
            code="transition_not_permitted",
        )

    text = state_machine.validate_comment(rule, comment)
    failures = state_machine.guard_failures(rule, locked)
    if "assignee_required" in failures:
        raise InvariantViolation(
            "Assign the ticket before moving it to this status.",
            code="assignee_required",
            fields={"assignee": ["An assignee is required for this transition."]},
        )

    previous_status = locked.status
    now = timezone.now()
    update_fields = ["status", "updated_at"]

    locked.status = to_status
    if rule.stamps_resolved_at:
        locked.resolved_at = now
        update_fields.append("resolved_at")
    if rule.clears_resolved_at:
        locked.resolved_at = None
        update_fields.append("resolved_at")
    if rule.stamps_closed_at:
        locked.closed_at = now
        update_fields.append("closed_at")
    if rule.clears_closed_at:
        locked.closed_at = None
        update_fields.append("closed_at")
    locked.save(update_fields=update_fields)

    history = TicketStatusHistory.objects.create(
        ticket=locked,
        from_status=previous_status,
        to_status=to_status,
        changed_by=actor,
        comment=text,
    )

    # The audit row references the history row instead of copying its payload: one fact, one owner
    # (ADR-011).
    audit_record(
        action=AuditAction.TICKET_STATUS_CHANGED,
        actor=actor,
        obj=locked,
        ticket=locked,
        metadata={
            "from": previous_status,
            "to": to_status,
            "history_id": str(history.pk),
            "comment": text[:200],
        },
        request=request,
    )

    # Everyone with an interest in the ticket hears about the move — except the person who made it.
    notify_status_changed(
        ticket=locked,
        actor=actor,
        from_status=previous_status,
        to_status=to_status,
        history_id=str(history.pk),
    )

    return history


def transitionable_roles() -> dict[str, list[str]]:
    """``{to_status: [roles]}`` — documentation helper for the workflow endpoint."""
    summary: dict[str, set[str]] = {}
    for rule in state_machine.TRANSITION_TABLE:
        summary.setdefault(rule.to_status, set()).update(rule.allowed_project_roles)
    return {status: sorted(roles) for status, roles in summary.items()}


def default_assignee_roles() -> list[str]:
    """Roles that may hold a ticket, exposed for the UI's assignee picker."""
    from apps.projects.models import ProjectRole as Role

    return [Role.ENGINEER, Role.MANAGER]


__all__ = [
    "ProjectRole",
    "allowed_transitions_for",
    "default_assignee_roles",
    "record_initial_status",
    "transition_ticket",
    "transitionable_roles",
]