"""Read queries for the audit trail.

Authorisation is expressed **in the query**, not in a later Python filter: a non-admin can only
ever load events whose project they belong to (directly, or through the ticket's project). Events
without project context — logins, role changes — are visible to administrators only, which is the
right default for security events.

"Foreign rows are simply absent" is the pattern used across the project: the API then returns
``404`` for something the user cannot see, instead of confirming its existence (NFR-1.3).
"""

from __future__ import annotations

from datetime import datetime

from django.db.models import Q, QuerySet

from apps.accounts.models import SystemRole, User
from apps.audit.models import AuditEvent

#: Related objects every audit response needs; centralised so the API layer cannot forget them
#: and accidentally produce N+1 queries.
RELATED_FIELDS = ("actor", "project", "ticket", "ticket__project")


def visible_events(actor: User) -> QuerySet[AuditEvent]:
    """Base queryset scoped to what ``actor`` is allowed to see."""
    queryset = AuditEvent.objects.select_related(*RELATED_FIELDS)

    if not actor or not actor.is_authenticated:
        return queryset.none()
    if actor.system_role == SystemRole.ADMIN:
        return queryset

    member_projects = actor.project_memberships.filter(is_active=True).values("project_id")
    return queryset.filter(
        Q(project_id__in=member_projects)
        | Q(ticket__project_id__in=member_projects)
    ).distinct()


def list_events(
    actor: User,
    *,
    project_id=None,
    ticket_id=None,
    action: str | None = None,
    object_type: str | None = None,
    actor_id=None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> QuerySet[AuditEvent]:
    """Filtered, permission-scoped audit list used by the API."""
    queryset = visible_events(actor)

    if project_id:
        queryset = queryset.filter(project_id=project_id)
    if ticket_id:
        queryset = queryset.filter(ticket_id=ticket_id)
    if action:
        queryset = queryset.filter(action=action)
    if object_type:
        queryset = queryset.filter(object_type=object_type)
    if actor_id:
        queryset = queryset.filter(actor_id=actor_id)
    if since:
        queryset = queryset.filter(created_at__gte=since)
    if until:
        queryset = queryset.filter(created_at__lte=until)

    return queryset


def recent_activity(actor: User, *, limit: int = 20, project_ids=None) -> QuerySet[AuditEvent]:
    """The "recent activity" feed on the dashboard (FR-9.4).

    ``project_ids`` lets the reports module narrow the feed to an already permission-scoped set of
    projects without re-deriving it.
    """
    queryset = visible_events(actor)
    if project_ids is not None:
        queryset = queryset.filter(
            Q(project_id__in=project_ids) | Q(ticket__project_id__in=project_ids)
        )
    return queryset.order_by("-created_at")[:limit]


def events_for_ticket(actor: User, ticket) -> QuerySet[AuditEvent]:
    """Full audit trail of one ticket, for its timeline."""
    return visible_events(actor).filter(ticket=ticket).order_by("-created_at")
