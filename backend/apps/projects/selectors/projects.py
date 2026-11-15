"""Project read queries.

Two rules are visible in every function here:

* **Permission is applied in SQL.** ``projects_visible_to`` filters in the database rather than
  fetching everything and discarding in Python: the latter is both slower and the classic place
  where a forgotten check leaks data.
* **Relations are joined eagerly.** ``select_related``/``prefetch_related`` and ``Count``
  annotations exist so a list endpoint issues a bounded number of queries instead of one per row
  (NFR-2.2).
"""

from __future__ import annotations

from django.db.models import Count, Exists, OuterRef, Q, QuerySet

from apps.accounts.models import SystemRole, User
from apps.projects.models import Component, Project, ProjectMembership, ProjectStatus

# Imported from the tickets module for the open-ticket counter. Safe direction: ``tickets.models``
# depends only on Django and ``common``, so ``projects -> tickets.models`` cannot create a cycle.
from apps.tickets.models import OPEN_STATUSES


def projects_visible_to(actor: User) -> QuerySet[Project]:
    """Every project the actor may see: all of them for Admins, memberships otherwise (FR-2.7).

    Implemented with ``Exists`` rather than ``filter(memberships__user=actor, ...)`` on purpose.

    Filtering on a multi-valued relation **joins** it, and a later ``annotate(Count("memberships"))``
    reuses that same join — so the count silently reports "1" (only the requesting user's row)
    instead of the real member count. Using a correlated ``EXISTS`` subquery keeps the two concerns
    separate: the filter is a predicate, and the annotation still sees every membership row.
    """
    if actor is None or not getattr(actor, "is_authenticated", False):
        return Project.objects.none()
    if actor.system_role == SystemRole.ADMIN:
        return Project.objects.all()

    membership_exists = ProjectMembership.objects.filter(
        project=OuterRef("pk"), user=actor, is_active=True
    )
    return Project.objects.filter(Exists(membership_exists))


def projects_with_counts(actor: User) -> QuerySet[Project]:
    """List queryset for the projects screen, with the numbers the UI shows.

    ``distinct=True`` matters: counting two different multi-valued relations in one query
    multiplies rows, and without it ``member_count`` would report the ticket count. This is the
    kind of bug that looks like a UI mistake.
    """
    return (
        projects_visible_to(actor)
        .select_related("owner")
        .annotate(
            member_count=Count("memberships", filter=Q(memberships__is_active=True), distinct=True),
            ticket_count=Count("tickets", distinct=True),
            open_ticket_count=Count(
                "tickets", filter=Q(tickets__status__in=list(OPEN_STATUSES)), distinct=True
            ),
        )
    )


def get_visible_project(actor: User, project_id) -> Project | None:
    """Fetch one project **only if** the actor may see it.

    Returning ``None`` instead of raising lets the API answer 404 uniformly for "no such project"
    and "not your project" (NFR-1.3).
    """
    return projects_visible_to(actor).filter(pk=project_id).first()


def projects_by_ids(actor: User, project_ids) -> QuerySet[Project]:
    return projects_visible_to(actor).filter(pk__in=list(project_ids))


def user_project_ids(actor: User) -> list:
    """Project ids the actor can see — used to scope aggregations in reports."""
    return list(projects_visible_to(actor).values_list("id", flat=True))


def project_memberships(project: Project, *, include_inactive: bool = False) -> QuerySet[ProjectMembership]:
    queryset = (
        ProjectMembership.objects.filter(project=project)
        .select_related("user", "user__profile")
        .order_by("role", "user__full_name")
    )
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset


def active_projects_for_user(user: User) -> QuerySet[Project]:
    """Projects where the user has an active membership — used by the profile screen."""
    return Project.objects.filter(memberships__user=user, memberships__is_active=True).distinct()


def project_components(project: Project, *, include_inactive: bool = False) -> QuerySet[Component]:
    queryset = Component.objects.filter(project=project).select_related("lead").order_by("name")
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset


def archived_projects(actor: User) -> QuerySet[Project]:
    return projects_visible_to(actor).filter(status=ProjectStatus.ARCHIVED)
