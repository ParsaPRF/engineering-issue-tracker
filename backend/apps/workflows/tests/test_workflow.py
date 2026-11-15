"""Workflow behaviour tests (FR-5.1 … FR-5.8).

Split deliberately:

* ``test_workflow.py`` — the *rules* (guards, stamps, history, authorisation), one scenario each;
* ``test_workflow_matrix.py`` — exhaustive coverage: every declared move for every project role, and
  every undeclared move rejected. That second file is what turns "we tested transitions" into "the
  transition table is what the code actually implements".
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.projects.models import ProjectMembership, ProjectRole
from apps.tickets.models import TicketStatus
from apps.tickets.tests.factories import TicketFactory
from apps.workflows.models import TicketStatusHistory
from apps.workflows.services import transition_ticket

pytestmark = pytest.mark.django_db


def transitions_url(ticket) -> str:
    return f"/api/v1/tickets/{ticket.id}/transitions/"


def history_url(ticket) -> str:
    return f"/api/v1/tickets/{ticket.id}/history/"


def error_code(response) -> str:
    return response.data["error"]["code"]


# ---------------------------------------------------------------------------
# Happy paths through the whole lifecycle
# ---------------------------------------------------------------------------
def test_full_lifecycle_from_new_to_closed(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter, assignee=team.engineer)
    client = client_for(team.manager)

    steps = [
        (TicketStatus.TRIAGED, None),
        (TicketStatus.IN_PROGRESS, None),
        (TicketStatus.IN_REVIEW, None),
        (TicketStatus.RESOLVED, "Verified on staging"),
        (TicketStatus.CLOSED, None),
    ]
    for to_status, comment in steps:
        payload = {"to_status": to_status}
        if comment:
            payload["comment"] = comment
        response = client.post(transitions_url(ticket), payload, format="json")
        assert response.status_code == 200, (to_status, response.data)
        assert response.data["status"] == to_status

    ticket.refresh_from_db()
    assert ticket.status == TicketStatus.CLOSED
    assert ticket.resolved_at is not None
    assert ticket.closed_at is not None

    # Every step is in the timeline, including the creation entry.
    timeline = list(TicketStatusHistory.objects.filter(ticket=ticket).order_by("created_at"))
    assert [row.to_status for row in timeline] == [
        TicketStatus.NEW,
        TicketStatus.TRIAGED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.IN_REVIEW,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    ]


def test_transition_records_history_and_audit_together(client_for, team):
    ticket = TicketFactory(project=team.project)

    client_for(team.manager).post(
        transitions_url(ticket), {"to_status": TicketStatus.TRIAGED, "comment": "Looks real"}, format="json"
    )

    history = TicketStatusHistory.objects.get(ticket=ticket, to_status=TicketStatus.TRIAGED)
    assert history.from_status == TicketStatus.NEW
    assert history.changed_by_id == team.manager.id
    assert history.comment == "Looks real"

    event = AuditEvent.objects.get(action=AuditAction.TICKET_STATUS_CHANGED, ticket=ticket)
    assert event.metadata["from"] == TicketStatus.NEW
    assert event.metadata["to"] == TicketStatus.TRIAGED
    # The audit row references the history row rather than duplicating it (ADR-011).
    assert event.metadata["history_id"] == str(history.pk)


def test_reopen_clears_resolution_timestamps(client_for, team):
    from django.utils import timezone

    ticket = TicketFactory(
        project=team.project,
        status=TicketStatus.CLOSED,
        assignee=team.engineer,
        resolved_at=timezone.now(),
        closed_at=timezone.now(),
    )

    response = client_for(team.reporter).post(
        transitions_url(ticket),
        {"to_status": TicketStatus.REOPENED, "comment": "Still broken on mobile"},
        format="json",
    )

    assert response.status_code == 200, response.data
    ticket.refresh_from_db()
    assert ticket.status == TicketStatus.REOPENED
    assert ticket.resolved_at is None
    assert ticket.closed_at is None


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
def test_invalid_jump_is_rejected(client_for, team):
    """NEW → RESOLVED skips triage and work: it must not be possible through the API."""
    ticket = TicketFactory(project=team.project)

    response = client_for(team.manager).post(
        transitions_url(ticket), {"to_status": TicketStatus.RESOLVED}, format="json"
    )

    assert response.status_code == 400
    assert error_code(response) == "invalid_transition"
    ticket.refresh_from_db()
    assert ticket.status == TicketStatus.NEW
    assert not TicketStatusHistory.objects.filter(ticket=ticket, to_status=TicketStatus.RESOLVED).exists()


def test_unknown_status_is_rejected(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.manager).post(transitions_url(ticket), {"to_status": "TELEPORTED"}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "invalid_status"


def test_noop_transition_is_rejected(client_for, team):
    ticket = TicketFactory(project=team.project, status=TicketStatus.TRIAGED)

    response = client_for(team.manager).post(
        transitions_url(ticket), {"to_status": TicketStatus.TRIAGED}, format="json"
    )

    assert response.status_code == 400
    assert error_code(response) == "noop_transition"


def test_rejection_requires_a_comment(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.manager).post(transitions_url(ticket), {"to_status": TicketStatus.REJECTED}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "comment_required"

    # A whitespace-only comment is not a comment.
    blank = client_for(team.manager).post(
        transitions_url(ticket), {"to_status": TicketStatus.REJECTED, "comment": "   "}, format="json"
    )
    assert blank.status_code == 400

    ok = client_for(team.manager).post(
        transitions_url(ticket),
        {"to_status": TicketStatus.REJECTED, "comment": "Not reproducible; closing as noise"},
        format="json",
    )
    assert ok.status_code == 200


def test_starting_work_requires_an_assignee(client_for, team):
    ticket = TicketFactory(project=team.project, status=TicketStatus.TRIAGED, assignee=None)

    response = client_for(team.manager).post(
        transitions_url(ticket), {"to_status": TicketStatus.IN_PROGRESS}, format="json"
    )

    assert response.status_code == 400
    assert error_code(response) == "assignee_required"
    ticket.refresh_from_db()
    assert ticket.status == TicketStatus.TRIAGED


def test_blocking_requires_a_reason(client_for, team):
    ticket = TicketFactory(project=team.project, status=TicketStatus.IN_PROGRESS, assignee=team.engineer)

    response = client_for(team.engineer).post(transitions_url(ticket), {"to_status": TicketStatus.BLOCKED}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "comment_required"


# ---------------------------------------------------------------------------
# Authorisation on transitions
# ---------------------------------------------------------------------------
@pytest.mark.security
def test_reporter_cannot_triage(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.reporter).post(
        transitions_url(ticket), {"to_status": TicketStatus.TRIAGED}, format="json"
    )

    assert response.status_code == 403
    assert error_code(response) == "transition_not_permitted"


@pytest.mark.security
def test_engineer_cannot_close(client_for, team):
    """Closing is a delivery decision reserved for project managers (workflow.md)."""
    from django.utils import timezone

    ticket = TicketFactory(
        project=team.project, status=TicketStatus.RESOLVED, assignee=team.engineer, resolved_at=timezone.now()
    )

    response = client_for(team.engineer).post(
        transitions_url(ticket), {"to_status": TicketStatus.CLOSED}, format="json"
    )

    assert response.status_code == 403


@pytest.mark.security
def test_outsider_cannot_transition_a_foreign_ticket(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.outsider).post(
        transitions_url(ticket), {"to_status": TicketStatus.TRIAGED}, format="json"
    )

    assert response.status_code == 404


def test_assignee_can_move_their_own_ticket_forward(client_for, team):
    ticket = TicketFactory(project=team.project, status=TicketStatus.TRIAGED, assignee=team.engineer)

    response = client_for(team.engineer).post(
        transitions_url(ticket), {"to_status": TicketStatus.IN_PROGRESS}, format="json"
    )

    assert response.status_code == 200, response.data


def test_admin_bypasses_project_roles(client_for, team):
    admin = UserFactory(system_role="ADMIN")
    ticket = TicketFactory(project=team.project, status=TicketStatus.RESOLVED, assignee=team.engineer)

    response = client_for(admin).post(transitions_url(ticket), {"to_status": TicketStatus.CLOSED}, format="json")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Endpoints that expose the workflow
# ---------------------------------------------------------------------------
def test_allowed_transitions_endpoint_matches_permissions(client_for, team):
    from django.utils import timezone

    ticket = TicketFactory(
        project=team.project, status=TicketStatus.RESOLVED, assignee=team.engineer, resolved_at=timezone.now()
    )

    manager_view = client_for(team.manager).get("/api/v1/workflows/transitions/", {"ticket": str(ticket.id)})
    engineer_view = client_for(team.engineer).get("/api/v1/workflows/transitions/", {"ticket": str(ticket.id)})

    assert manager_view.status_code == 200
    manager_targets = {row["to_status"] for row in manager_view.data["allowed"]}
    engineer_targets = {row["to_status"] for row in engineer_view.data["allowed"]}

    assert manager_targets == {TicketStatus.CLOSED, TicketStatus.REOPENED}
    assert engineer_targets == {TicketStatus.REOPENED}  # engineers may reopen, not close


def test_allowed_transitions_reports_blocking_preconditions(client_for, team):
    ticket = TicketFactory(project=team.project, status=TicketStatus.TRIAGED, assignee=None)

    response = client_for(team.manager).get("/api/v1/workflows/transitions/", {"ticket": str(ticket.id)})

    start = next(row for row in response.data["allowed"] if row["to_status"] == TicketStatus.IN_PROGRESS)
    assert start["available"] is False
    assert start["blocked_by"] == ["assignee_required"]


def test_allowed_transitions_requires_the_ticket_parameter(client_for, team):
    response = client_for(team.manager).get("/api/v1/workflows/transitions/")

    assert response.status_code == 400
    assert error_code(response) == "validation_error"


def test_history_endpoint_returns_the_timeline(client_for, team):
    ticket = TicketFactory(project=team.project)
    client_for(team.manager).post(transitions_url(ticket), {"to_status": TicketStatus.TRIAGED}, format="json")

    response = client_for(team.reporter).get(history_url(ticket))

    assert response.status_code == 200
    assert [row["to_status"] for row in response.data] == [TicketStatus.NEW, TicketStatus.TRIAGED]
    assert response.data[0]["from_status"] is None
    assert response.data[0]["changed_by_name"]


def test_workflow_catalogue_is_available(client_for, team):
    response = client_for(team.engineer).get("/api/v1/workflows/")

    assert response.status_code == 200
    assert len(response.data["statuses"]) == len(TicketStatus.values)
    assert response.data["declared_move_count"] == len(response.data["transitions"])


def test_transition_service_is_the_only_writer(monkeypatch, team):
    """A direct model save must not be how status changes in application code.

    This test documents the convention and guards against a future refactor that starts writing
    ``ticket.status`` from a serializer: the service attaches a history row, and a raw save does not
    — so the timeline/status mismatch is detectable.
    """
    ticket = TicketFactory(project=team.project)
    ticket.status = TicketStatus.RESOLVED
    ticket.save(update_fields=["status"])

    assert not TicketStatusHistory.objects.filter(ticket=ticket, to_status=TicketStatus.RESOLVED).exists()

    # Through the service, the timeline is always in sync.
    other = TicketFactory(project=team.project, status=TicketStatus.IN_REVIEW, assignee=team.engineer)
    transition_ticket(ticket=other, to_status=TicketStatus.RESOLVED, actor=team.manager, comment="ok")
    assert TicketStatusHistory.objects.filter(ticket=other, to_status=TicketStatus.RESOLVED).exists()


def test_engineer_role_absence_is_enforced_by_the_kernel_not_the_view(client_for, team):
    """Removing the membership must make the same call fail — authorisation is not cached in the UI."""
    ticket = TicketFactory(project=team.project, status=TicketStatus.TRIAGED, assignee=team.engineer)
    client = client_for(team.engineer)
    assert client.post(transitions_url(ticket), {"to_status": TicketStatus.IN_PROGRESS}, format="json").status_code == 200

    ProjectMembership.objects.filter(project=team.project, user=team.engineer).update(is_active=False)

    blocked = client.post(transitions_url(ticket), {"to_status": TicketStatus.BLOCKED, "comment": "x"}, format="json")
    assert blocked.status_code == 404  # no longer a member: the ticket is not even visible

    # Silence the unused-import warning for ProjectRole while keeping the import intent explicit.
    assert ProjectRole.REPORTER in ProjectRole.values