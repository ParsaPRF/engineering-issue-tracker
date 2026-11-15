"""Ticket read queries.

Every list/detail path starts from :func:`visible_tickets`, which is the *only* place that decides
which tickets exist for a caller. That single choke point is what makes cross-project leaks hard:
a new endpoint that forgets ``project__in=visible projects`` still cannot see foreign tickets if it
goes through this selector — and the review checklist says "start from visible_tickets".
"""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from apps.projects.selectors.projects import projects_visible_to
from apps.tickets.models import DONE_STATUSES, OPEN_STATUSES, Ticket


def ticket_queryset() -> QuerySet[Ticket]:
    """Base queryset with every relation the API renders joined.

    Without these joins the ticket list issues one query per row for project, reporter, assignee and
    component — the classic N+1 that only shows up once there is real data (NFR-2.2).
    """
    return Ticket.objects.select_related(
        "project",
        "component",
        "reporter",
        "reporter__profile",
        "assignee",
        "assignee__profile",
    ).prefetch_related("labels")


def with_counts(queryset: QuerySet[Ticket]) -> QuerySet[Ticket]:
    """Annotate comment/attachment counts for list badges."""
    return queryset.annotate(
        comment_count=Count("comments", filter=Q(comments__is_deleted=False), distinct=True),
        attachment_count=Count("attachments", filter=Q(attachments__is_deleted=False), distinct=True),
    )


def visible_tickets(actor) -> QuerySet[Ticket]:
    """Tickets in the projects the actor may see (FR-3.8)."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return Ticket.objects.none()
    return ticket_queryset().filter(project__in=projects_visible_to(actor))


def get_visible_ticket(actor, ticket_id) -> Ticket | None:
    """Fetch one ticket only if visible; ``None`` lets the API answer 404 for foreign ids."""
    if not ticket_id:
        return None
    return visible_tickets(actor).filter(pk=ticket_id).first()


def my_assignments(actor, *, include_done: bool = False) -> QuerySet[Ticket]:
    """Tickets assigned to the actor (FR-4.4).

    Defaults to open work only: "my tasks" means what still needs attention, while
    ``include_done=true`` supports a history view.
    """
    queryset = visible_tickets(actor).filter(assignee=actor)
    if not include_done:
        queryset = queryset.filter(status__in=list(OPEN_STATUSES))
    return queryset.order_by("-priority", "due_date", "-created_at")


def project_tickets(actor, project) -> QuerySet[Ticket]:
    return visible_tickets(actor).filter(project=project)


def overdue_tickets(actor) -> QuerySet[Ticket]:
    """Open tickets past their due date (used by the dashboard "at risk" list)."""
    from django.utils import timezone

    return (
        visible_tickets(actor)
        .filter(due_date__lt=timezone.localdate(), status__in=list(OPEN_STATUSES))
        .order_by("due_date")
    )


def unassigned_open_tickets(actor) -> QuerySet[Ticket]:
    return visible_tickets(actor).filter(assignee__isnull=True, status__in=list(OPEN_STATUSES))


def recently_resolved(actor, *, limit: int = 10) -> QuerySet[Ticket]:
    return (
        visible_tickets(actor)
        .filter(status__in=list(DONE_STATUSES))
        .order_by("-resolved_at", "-updated_at")[:limit]
    )