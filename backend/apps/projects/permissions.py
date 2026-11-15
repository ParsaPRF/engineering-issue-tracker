"""The permission kernel (ADR-012).

**Every** object-level authorisation decision in the project is one of the functions below. They
are deliberately plain functions rather than DRF permission classes because the same rule has to be
enforced in three different places:

1. the API layer, to reject a request early with the right status code;
2. the service layer, because the API is not the only writer (management commands, Celery tasks,
   tests and the Django admin exist too);
3. tests, which can assert the matrix of roles × actions directly, without HTTP.

Rules of the house for this module:

* **Pure.** No writes, no side effects, no logging. Given ``(actor, object)`` the answer is a bool
  (or a set of allowed field names).
* **Fail closed.** An unknown user, an archived project, an inactive membership or a missing
  membership all mean "no". Never raise for a *denied* check; callers decide between 403 and 404.
* **One direction of dependency.** This module imports ``accounts`` and ``projects`` models only.
  The workflow module passes its own transition rules *in* (see ``can_transition_ticket``), so
  ``projects`` never has to know about the state machine.
* **No HTTP vocabulary.** There is no ``request`` here — only an actor (a ``User``).
"""

from __future__ import annotations

from collections.abc import Iterable

from apps.accounts.roles import SystemRole
from apps.projects.models import Component, Project, ProjectMembership, ProjectRole, ProjectStatus

# ---------------------------------------------------------------------------
# Membership primitives
# ---------------------------------------------------------------------------


def get_membership(actor, project: Project) -> ProjectMembership | None:
    """Return the actor's active membership of ``project``, or ``None``.

    Returns ``None`` for an anonymous actor so callers never have to guard for it.
    """
    if actor is None or not getattr(actor, "is_authenticated", False) or not actor.is_active:
        return None
    return (
        ProjectMembership.objects.filter(project=project, user=actor, is_active=True)
        .select_related("user")
        .first()
    )


def get_project_role(actor, project: Project) -> str | None:
    """The actor's project role, or ``None`` when they have no active membership."""
    membership = get_membership(actor, project)
    return membership.role if membership else None


def is_admin(actor) -> bool:
    """Global administrators operate the installation and bypass membership checks."""
    return bool(
        actor
        and getattr(actor, "is_authenticated", False)
        and actor.is_active
        and actor.system_role == SystemRole.ADMIN
    )


def is_active_member(actor, project: Project) -> bool:
    return is_admin(actor) or get_membership(actor, project) is not None


def has_project_role(actor, project: Project, roles: Iterable[str]) -> bool:
    """True when the actor holds one of ``roles`` in this project (Admins always qualify)."""
    if is_admin(actor):
        return True
    role = get_project_role(actor, project)
    return role is not None and role in set(roles)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


def can_view_project(actor, project: Project) -> bool:
    """FR-2.7: members and Admins only. Archived projects stay readable."""
    return is_active_member(actor, project)


def can_manage_project(actor, project: Project) -> bool:
    """Edit project fields, archive/restore, rename: owner, project managers, Admins."""
    if is_admin(actor):
        return True
    if project.owner_id and project.owner_id == getattr(actor, "id", None):
        return True
    return has_project_role(actor, project, {ProjectRole.MANAGER})


def can_manage_members(actor, project: Project) -> bool:
    """Add, remove or re-role members. Same capability set as managing the project itself."""
    return can_manage_project(actor, project)


def can_manage_components(actor, project: Project) -> bool:
    """Components are project structure: managers (and Admins) own them.

    Engineers may still *use* components by setting ``component`` on a ticket they can edit.
    """
    return can_manage_project(actor, project)


def can_create_project(actor) -> bool:
    """Only Admins and Project Managers may open a project (FR-2.1)."""
    if not (actor and getattr(actor, "is_authenticated", False) and actor.is_active):
        return False
    return actor.system_role in {SystemRole.ADMIN, SystemRole.PROJECT_MANAGER}


# ---------------------------------------------------------------------------
# Membership eligibility
# ---------------------------------------------------------------------------


def is_eligible_assignee(actor, project: Project) -> bool:
    """Who may be given a ticket: an active member whose project role carries a workload.

    Reporters are intentionally excluded (assumption A-14): they file and follow work, they are not
    the queue. This is the single place that decides it, so ``tickets.services.assign_ticket`` and
    the API cannot disagree.
    """
    if actor is None or not getattr(actor, "is_active", False):
        return False
    role = get_project_role(actor, project)
    return role in {ProjectRole.ENGINEER, ProjectRole.MANAGER}


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


def can_edit_component(actor, component: Component) -> bool:
    return can_manage_components(actor, component.project)


# ---------------------------------------------------------------------------
# Ticket — expressed against a "ticket-like" object
# ---------------------------------------------------------------------------
# These functions take any object exposing ``project`` and ``reporter_id``/``assignee_id``. That
# keeps the kernel usable for draft/update payloads and for ``Ticket`` alike, and avoids importing
# the tickets app from here.


def _ticket_project(ticket):
    return ticket.project


def can_view_ticket(actor, ticket) -> bool:
    """Read access follows project membership. Foreign tickets are simply *not visible*, which the
    API turns into 404 rather than 403 so existence is not confirmed (NFR-1.3)."""
    return can_view_project(actor, _ticket_project(ticket))


def can_edit_ticket(actor, ticket) -> bool:
    """Who may change *some* ticket fields at all.

    Field-level granularity is in :func:`editable_ticket_fields`; this predicate answers the
    coarser question and is the one used for 403/404 decisions.
    """
    if is_admin(actor) or has_project_role(actor, ticket.project, {ProjectRole.MANAGER}):
        return True
    if getattr(ticket, "assignee_id", None) and ticket.assignee_id == getattr(actor, "id", None):
        return True
    # Reporters may correct the report they filed, unless the ticket is already closed.
    if getattr(ticket, "reporter_id", None) and ticket.reporter_id == getattr(actor, "id", None):
        return True
    return False


#: Fields a reporter may change on their own ticket (before it is closed).
REPORTER_EDITABLE_FIELDS = frozenset({"title", "description", "type", "severity", "priority"})

#: Fields a contributor (assignee) may change while working the ticket.
CONTRIBUTOR_EDITABLE_FIELDS = REPORTER_EDITABLE_FIELDS | frozenset({"component", "due_date"})

#: Fields only managers/Admins may change.
MANAGER_ONLY_FIELDS = frozenset(
    {
        "title",
        "description",
        "type",
        "severity",
        "priority",
        "component",
        "due_date",
        "labels",
    }
)

#: Never editable through the API, by anyone. ``status`` is here because it changes only through
#: the transition operation (ADR-005); the rest are immutable history.
IMMUTABLE_TICKET_FIELDS = frozenset({"key", "project", "reporter", "status", "created_at", "resolved_at", "closed_at"})


def editable_ticket_fields(actor, ticket) -> frozenset[str]:
    """Field names ``actor`` may write on ``ticket``.

    Returning a *set* rather than a bool moves the whole "who may change what" question into one
    table, so the serializer cannot quietly drift from the rules: it intersects the submitted
    payload with this set.
    """
    if is_admin(actor) or has_project_role(actor, ticket.project, {ProjectRole.MANAGER}):
        return MANAGER_ONLY_FIELDS

    fields: set[str] = set()
    user_id = getattr(actor, "id", None)

    if ticket.assignee_id and ticket.assignee_id == user_id:
        fields |= CONTRIBUTOR_EDITABLE_FIELDS

    if ticket.reporter_id and ticket.reporter_id == user_id and not ticket.is_done:
        fields |= REPORTER_EDITABLE_FIELDS

    return frozenset(fields)


def can_create_ticket(actor, project: Project) -> bool:
    """Any active member may report work; archived projects accept none (FR-2.4)."""
    if project.status == ProjectStatus.ARCHIVED:
        return False
    return is_active_member(actor, project)


def can_assign_ticket(actor, ticket) -> bool:
    """Managers and Admins assign anyone; an engineer may take an *unassigned* ticket."""
    if is_admin(actor) or has_project_role(actor, ticket.project, {ProjectRole.MANAGER}):
        return True
    if getattr(ticket, "assignee_id", None) is None:
        return has_project_role(actor, ticket.project, {ProjectRole.ENGINEER})
    return False


def can_transition_ticket(
    actor,
    ticket,
    *,
    allowed_project_roles: Iterable[str],
    allow_assignee: bool = False,
) -> bool:
    """Authorise one workflow transition.

    The *rule* (which statuses are reachable and who may reach them) belongs to the state machine in
    ``apps.workflows``; this function only evaluates it against the actor. That inversion is what
    keeps the dependency direction one-way: ``workflows`` imports ``projects.permissions``, never the
    reverse.
    """
    if not can_view_ticket(actor, ticket):
        return False
    if is_admin(actor):
        return True

    role = get_project_role(actor, ticket.project)
    if role is None:
        return False
    if role in set(allowed_project_roles):
        return True
    if allow_assignee and getattr(ticket, "assignee_id", None) == getattr(actor, "id", None):
        return True
    return False


def can_change_labels(actor, ticket) -> bool:
    return can_edit_ticket(actor, ticket)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def can_comment(actor, ticket) -> bool:
    """Discussion is open to every member of the project, including reporters."""
    return can_view_ticket(actor, ticket)


def can_edit_comment(actor, comment) -> bool:
    """Only the author, and only within the configured window (FR-6.2).

    Admins may moderate rather than edit: rewriting somebody's words would make the audit trail a
    fiction, so moderation is deletion, which is recorded.
    """
    return getattr(comment, "author_id", None) == getattr(actor, "id", None)


def can_delete_comment(actor, comment) -> bool:
    """Authors may withdraw their own comment; managers and Admins may moderate any (FR-6.3)."""
    if getattr(comment, "author_id", None) == getattr(actor, "id", None):
        return True
    ticket = comment.ticket
    return is_admin(actor) or has_project_role(actor, ticket.project, {ProjectRole.MANAGER})


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


def can_attach_to_ticket(actor, ticket) -> bool:
    return can_view_ticket(actor, ticket)


def can_delete_attachment(actor, attachment) -> bool:
    """Uploader, project managers and Admins may delete an attachment."""
    if getattr(attachment, "uploader_id", None) == getattr(actor, "id", None):
        return True
    ticket = attachment.effective_ticket
    if ticket is None:  # pragma: no cover - the check constraint prevents this
        return is_admin(actor)
    return is_admin(actor) or has_project_role(actor, ticket.project, {ProjectRole.MANAGER})
