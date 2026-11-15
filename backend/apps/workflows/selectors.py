"""Workflow read queries: the ticket timeline and the transition catalogue."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.workflows.models import TicketStatusHistory


def ticket_history(ticket) -> QuerySet[TicketStatusHistory]:
    """Full status timeline of one ticket, oldest first.

    ``select_related("changed_by")`` because the timeline is rendered with the actor's name; without
    it the endpoint would issue one query per row.
    """
    return (
        TicketStatusHistory.objects.filter(ticket=ticket)
        .select_related("changed_by")
        .order_by("created_at")
    )


def transition_catalogue() -> tuple[list[dict], list[dict]]:
    """The whole lifecycle as data: ``(transitions, statuses)``.

    Exposed so clients (and the generated API docs) can render the workflow without hard-coding it.
    """
    from apps.tickets.models import TicketStatus
    from apps.workflows.state_machine import TRANSITION_TABLE

    return [
        {
            "from_status": rule.from_status,
            "to_status": rule.to_status,
            "label": rule.label or rule.to_status.replace("_", " ").title(),
            "allowed_project_roles": sorted(rule.allowed_project_roles),
            "allow_assignee": rule.allow_assignee,
            "requires_comment": rule.requires_comment,
            "requires_assignee": rule.requires_assignee,
        }
        for rule in TRANSITION_TABLE
    ], [{"value": status.value, "label": status.label} for status in TicketStatus]