"""Aggregation queries for dashboards and reports.

This module owns every number the UI displays, for three reasons:

1. **One place to get permission scoping right.** All aggregations start from the caller's visible
   projects, so a new chart cannot accidentally include another project's data (FR-9.5).
2. **One place to keep queries bounded.** Everything here is a grouped ``values().annotate()`` or an
   ``aggregate()`` — never a Python loop over rows (NFR-2.5).
3. **No cycles.** ``reports`` sits at the top of the dependency graph: it imports other modules, and
   nothing imports it at module level. Callers inside those modules import it inside a function.
"""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from apps.accounts.models import User
from apps.projects.models import Project
from apps.projects.selectors.projects import projects_visible_to
from apps.tickets.models import DONE_STATUSES, OPEN_STATUSES, Priority, Severity, Ticket, TicketStatus


def _scoped_tickets(actor: User, *, project: Project | None = None) -> QuerySet[Ticket]:
    """Tickets the actor may see, optionally narrowed to one project."""
    queryset = Ticket.objects.filter(project__in=projects_visible_to(actor))
    if project is not None:
        queryset = queryset.filter(project=project)
    return queryset


def _breakdown(queryset: QuerySet[Ticket], field: str) -> dict[str, int]:
    """Grouped counts for one field, with zeroes filled in for choices that do not appear.

    Filling zeroes matters for the UI: a chart that silently omits ``CRITICAL`` because there are no
    critical tickets looks like a bug, and an absent key would crash a naive frontend.
    """
    counts = {row[field]: row["count"] for row in queryset.values(field).annotate(count=Count("id"))}

    if field == "status":
        keys = TicketStatus.values
    elif field == "priority":
        keys = Priority.values
    elif field == "severity":
        keys = Severity.values
    else:
        keys = list(counts)
    return {key: counts.get(key, 0) for key in keys}


def project_statistics(actor: User, project: Project) -> dict:
    """Statistics for one project (FR-2.8). The caller must already have established access."""
    queryset = _scoped_tickets(actor, project=project)
    # One query for all headline numbers instead of eight: aggregate() maps directly onto a single
    # SQL statement with conditional counts.
    totals = queryset.aggregate(
        total_tickets=Count("id"),
        open_tickets=Count("id", filter=Q(status__in=list(OPEN_STATUSES))),
        resolved_tickets=Count("id", filter=Q(status=TicketStatus.RESOLVED)),
        closed_tickets=Count("id", filter=Q(status=TicketStatus.CLOSED)),
        blocked_tickets=Count("id", filter=Q(status=TicketStatus.BLOCKED)),
        unassigned_tickets=Count("id", filter=Q(assignee__isnull=True) & Q(status__in=list(OPEN_STATUSES))),
    )

    return {
        "project_id": str(project.id),
        "project_key": project.key,
        "project_name": project.name,
        **totals,
        "by_status": _breakdown(queryset, "status"),
        "by_priority": _breakdown(queryset, "priority"),
        "by_severity": _breakdown(queryset, "severity"),
        "by_type": _breakdown(queryset, "type"),
        "done_tickets": queryset.filter(status__in=list(DONE_STATUSES)).count(),
    }


def dashboard(actor: User, *, project_ids: list | None = None) -> dict:
    """The main dashboard payload (FR-9.1, FR-9.2).

    ``project_ids`` optionally narrows the view to a selection of projects (the UI's project
    filter). The list is intersected with what the actor may see, so passing somebody else's project
    id can only ever *reduce* the result set, never widen it.
    """
    queryset = _scoped_tickets(actor)
    if project_ids:
        # Query params arrive as strings while ``values_list`` yields UUID objects; comparing them
        # directly silently filtered everything out. Normalise both sides.
        visible_ids = {str(pid) for pid in _scoped_tickets(actor).values_list("project_id", flat=True)}
        queryset = queryset.filter(project_id__in=[pid for pid in project_ids if str(pid) in visible_ids])

    totals = queryset.aggregate(
        total_tickets=Count("id"),
        open_tickets=Count("id", filter=Q(status__in=list(OPEN_STATUSES))),
        resolved_tickets=Count("id", filter=Q(status=TicketStatus.RESOLVED)),
        closed_tickets=Count("id", filter=Q(status=TicketStatus.CLOSED)),
        blocked_tickets=Count("id", filter=Q(status=TicketStatus.BLOCKED)),
        unassigned_tickets=Count("id", filter=Q(assignee__isnull=True) & Q(status__in=list(OPEN_STATUSES))),
    )

    by_project = [
        {
            "project_id": str(row["project_id"]),
            "project_key": row["project__key"],
            "project_name": row["project__name"],
            "total_tickets": row["count"],
            "open_tickets": row["open_count"],
        }
        for row in queryset.values("project_id", "project__key", "project__name")
        .annotate(
            count=Count("id"),
            open_count=Count("id", filter=Q(status__in=list(OPEN_STATUSES))),
        )
        .order_by("-count")
    ]

    return {
        "totals": totals,
        "by_status": _breakdown(queryset, "status"),
        "by_priority": _breakdown(queryset, "priority"),
        "by_severity": _breakdown(queryset, "severity"),
        "by_type": _breakdown(queryset, "type"),
        "by_project": by_project,
        "project_count": projects_visible_to(actor).count(),
    }


def engineer_workload(actor: User, *, project_ids: list | None = None) -> list[dict]:
    """Open tickets per engineer (FR-9.3), scoped to visible projects.

    Assignees with no open tickets are included: "who is free?" is as important as "who is loaded?".
    """
    from apps.projects.models import ProjectMembership, ProjectRole

    queryset = _scoped_tickets(actor)
    if project_ids:
        queryset = queryset.filter(project_id__in=project_ids)

    counts = (
        queryset.filter(assignee__isnull=False)
        .values("assignee_id", "assignee__full_name", "assignee__email")
        .annotate(
            open_tickets=Count("id", filter=Q(status__in=list(OPEN_STATUSES))),
            total_tickets=Count("id"),
            blocked_tickets=Count("id", filter=Q(status=TicketStatus.BLOCKED)),
        )
        .order_by("-open_tickets")
    )

    engineers = (
        ProjectMembership.objects.filter(
            project__in=projects_visible_to(actor),
            is_active=True,
            role__in=[ProjectRole.ENGINEER, ProjectRole.MANAGER],
        )
        .values("user_id", "user__full_name", "user__email")
        .distinct()
    )

    workload = {
        row["assignee_id"]: {
            "user_id": str(row["assignee_id"]),
            "full_name": row["assignee__full_name"],
            "email": row["assignee__email"],
            "open_tickets": row["open_tickets"],
            "total_tickets": row["total_tickets"],
            "blocked_tickets": row["blocked_tickets"],
        }
        for row in counts
    }

    for row in engineers:
        workload.setdefault(
            row["user_id"],
            {
                "user_id": str(row["user_id"]),
                "full_name": row["user__full_name"],
                "email": row["user__email"],
                "open_tickets": 0,
                "total_tickets": 0,
                "blocked_tickets": 0,
            },
        )

    return sorted(workload.values(), key=lambda row: (-row["open_tickets"], row["full_name"] or ""))


def my_workload(actor: User) -> dict:
    """The signed-in user's own task summary (used by "My assignments")."""
    queryset = _scoped_tickets(actor).filter(assignee=actor)
    return {
        "open_tickets": queryset.filter(status__in=list(OPEN_STATUSES)).count(),
        "total_tickets": queryset.count(),
        "by_status": _breakdown(queryset, "status"),
        "by_priority": _breakdown(queryset, "priority"),
    }
