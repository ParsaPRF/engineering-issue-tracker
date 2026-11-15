"""Ticket API tests (FR-3.1 … FR-3.9).

The permission premise of each test is built explicitly through the ``team`` fixture: manager,
engineer, reporter, and an outsider who belongs to no project.
"""

from __future__ import annotations

import pytest

from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.projects.models import ProjectMembership, ProjectRole
from apps.projects.tests.factories import ComponentFactory
from apps.tickets.models import Priority, Severity, Ticket, TicketStatus, TicketType
from apps.tickets.tests.factories import TicketFactory
from apps.workflows.models import TicketStatusHistory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/tickets/"


def detail_url(ticket) -> str:
    return f"/api/v1/tickets/{ticket.id}/"


def error_code(response) -> str:
    return response.data["error"]["code"]


def create_payload(project, **overrides) -> dict:
    payload = {
        "project": str(project.id),
        "title": "Checkout fails with a 500",
        "description": "Steps:\n1. add item\n2. pay\n\nExpected 200, got 500",
        "type": TicketType.BUG,
        "priority": Priority.HIGH,
        "severity": Severity.CRITICAL,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def test_member_can_create_ticket_with_generated_key_and_new_status(client_for, team):
    response = client_for(team.reporter).post(LIST_URL, create_payload(team.project), format="json")

    assert response.status_code == 201, response.data
    ticket = Ticket.objects.get(key=response.data["key"])
    assert ticket.key.startswith(f"{team.project.key}-")
    assert ticket.status == TicketStatus.NEW  # always starts at NEW
    assert ticket.reporter_id == team.reporter.id  # reporter comes from the session, not the payload
    assert ticket.priority == Priority.HIGH and ticket.severity == Severity.CRITICAL
    assert response.data["assignee"] is None


def test_ticket_creation_opens_the_timeline_and_the_audit_trail(client_for, team):
    response = client_for(team.reporter).post(LIST_URL, create_payload(team.project), format="json")
    ticket = Ticket.objects.get(pk=response.data["id"])

    history = TicketStatusHistory.objects.get(ticket=ticket)
    assert history.from_status is None
    assert history.to_status == TicketStatus.NEW
    assert history.changed_by_id == team.reporter.id

    assert AuditEvent.objects.filter(action=AuditAction.TICKET_CREATED, ticket=ticket).exists()


def test_client_cannot_forge_status_on_creation(client_for, team):
    payload = create_payload(team.project, status=TicketStatus.CLOSED)

    response = client_for(team.reporter).post(LIST_URL, payload, format="json")

    assert response.status_code == 201
    ticket = Ticket.objects.get(pk=response.data["id"])
    assert ticket.status == TicketStatus.NEW  # unknown fields are ignored, never honoured


def test_client_cannot_forge_reporter(client_for, team):
    payload = create_payload(team.project, reporter=str(team.manager.id))

    response = client_for(team.reporter).post(LIST_URL, payload, format="json")

    assert response.status_code == 201
    assert Ticket.objects.get(pk=response.data["id"]).reporter_id == team.reporter.id


@pytest.mark.security
def test_outsider_cannot_create_ticket(client_for, team):
    response = client_for(team.outsider).post(LIST_URL, create_payload(team.project), format="json")

    assert response.status_code == 404  # the project is not visible at all
    assert not Ticket.objects.exists()


def test_archived_project_rejects_new_tickets(client_for, team):
    team.project.archive()

    response = client_for(team.manager).post(LIST_URL, create_payload(team.project), format="json")

    assert response.status_code == 400
    assert error_code(response) == "project_archived"


def test_component_from_another_project_is_rejected(client_for, team):
    from apps.projects.tests.factories import ProjectFactory

    foreign_component = ComponentFactory(project=ProjectFactory(key="OTHER"))

    response = client_for(team.manager).post(
        LIST_URL, create_payload(team.project, component=str(foreign_component.id)), format="json"
    )

    assert response.status_code == 404


def test_reporter_role_member_cannot_be_the_assignee(client_for, team):
    """Assignment eligibility is a rule, not a UI preference (assumption A-14)."""
    response = client_for(team.manager).post(
        LIST_URL, create_payload(team.project, assignee=str(team.reporter.id)), format="json"
    )

    assert response.status_code == 400
    assert error_code(response) == "ineligible_assignee"


def test_engineer_cannot_assign_somebody_else_on_creation(client_for, team):
    response = client_for(team.engineer).post(
        LIST_URL, create_payload(team.project, assignee=str(team.manager.id)), format="json"
    )

    assert response.status_code == 403


def test_manager_can_assign_at_creation(client_for, team):
    response = client_for(team.manager).post(
        LIST_URL, create_payload(team.project, assignee=str(team.engineer.id)), format="json"
    )

    assert response.status_code == 201
    assert response.data["assignee"]["id"] == str(team.engineer.id)


# ---------------------------------------------------------------------------
# Status is not a writable field (ADR-005)
# ---------------------------------------------------------------------------
def test_patch_status_is_rejected_with_a_helpful_error(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter)

    response = client_for(team.manager).patch(detail_url(ticket), {"status": TicketStatus.CLOSED}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "use_transition_endpoint"
    ticket.refresh_from_db()
    assert ticket.status == TicketStatus.NEW


def test_patch_assignee_is_rejected_in_favour_of_the_assign_endpoint(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter)

    response = client_for(team.manager).patch(detail_url(ticket), {"assignee": str(team.engineer.id)}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "use_assignment_endpoint"


def test_key_and_project_are_immutable(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter)
    original_key = ticket.key

    response = client_for(team.manager).patch(
        detail_url(ticket), {"key": "HACK-1", "project": str(team.project.id), "title": "Renamed"}, format="json"
    )

    assert response.status_code == 200
    ticket.refresh_from_db()
    assert ticket.key == original_key
    assert ticket.title == "Renamed"


# ---------------------------------------------------------------------------
# Update permissions (FR-3.9)
# ---------------------------------------------------------------------------
def test_reporter_can_edit_their_own_ticket(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter)

    response = client_for(team.reporter).patch(
        detail_url(ticket), {"title": "Better title", "priority": Priority.LOW}, format="json"
    )

    assert response.status_code == 200
    ticket.refresh_from_db()
    assert ticket.title == "Better title"
    assert ticket.priority == Priority.LOW


def test_reporter_cannot_edit_a_closed_ticket(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter, status=TicketStatus.CLOSED)

    response = client_for(team.reporter).patch(detail_url(ticket), {"title": "zombie"}, format="json")

    assert response.status_code == 403


def test_reporter_cannot_edit_someone_elses_ticket(client_for, team):
    from apps.accounts.tests.factories import UserFactory

    someone_else = UserFactory()
    ProjectMembership.objects.create(project=team.project, user=someone_else, role=ProjectRole.REPORTER)
    ticket = TicketFactory(project=team.project, reporter=someone_else)

    response = client_for(team.reporter).patch(detail_url(ticket), {"title": "hijack"}, format="json")

    assert response.status_code == 403
    assert error_code(response) == "permission_denied"


def test_assignee_can_edit_working_fields(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter, assignee=team.engineer)
    component = ComponentFactory(project=team.project, name="Checkout")

    response = client_for(team.engineer).patch(
        detail_url(ticket), {"component": str(component.id), "severity": Severity.MINOR}, format="json"
    )

    assert response.status_code == 200
    ticket.refresh_from_db()
    assert ticket.component_id == component.id
    assert ticket.severity == Severity.MINOR


def test_manager_can_edit_any_ticket(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter)

    response = client_for(team.manager).patch(detail_url(ticket), {"title": "Manager edit"}, format="json")

    assert response.status_code == 200


def test_update_is_audited_with_the_changed_fields(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter)

    client_for(team.manager).patch(detail_url(ticket), {"title": "Audited"}, format="json")

    event = AuditEvent.objects.get(action=AuditAction.TICKET_UPDATED, ticket=ticket)
    assert event.metadata["changed"]["title"]["to"] == "Audited"


# ---------------------------------------------------------------------------
# Visibility (FR-3.8)
# ---------------------------------------------------------------------------
@pytest.mark.security
def test_ticket_list_never_contains_foreign_projects(client_for, team):
    TicketFactory(project=team.project, title="Mine")

    response = client_for(team.outsider).get(LIST_URL)

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.security
def test_foreign_ticket_detail_is_404(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.outsider).get(detail_url(ticket))

    assert response.status_code == 404


def test_ticket_list_is_paginated(client_for, team):
    for _ in range(3):
        TicketFactory(project=team.project)

    response = client_for(team.engineer).get(LIST_URL, {"page_size": 2})

    assert response.status_code == 200
    assert response.data["count"] == 3
    assert len(response.data["results"]) == 2


# ---------------------------------------------------------------------------
# Filtering, search, ordering (FR-3.7)
# ---------------------------------------------------------------------------
def test_filter_by_multiple_statuses(client_for, team):
    TicketFactory(project=team.project, status=TicketStatus.NEW)
    TicketFactory(project=team.project, status=TicketStatus.IN_PROGRESS)
    TicketFactory(project=team.project, status=TicketStatus.CLOSED)

    response = client_for(team.manager).get(LIST_URL, {"status": f"{TicketStatus.NEW},{TicketStatus.IN_PROGRESS}"})

    assert response.status_code == 200
    assert response.data["count"] == 2


def test_filter_by_assignee_and_unassigned(client_for, team):
    TicketFactory(project=team.project, assignee=team.engineer)
    TicketFactory(project=team.project)

    by_assignee = client_for(team.manager).get(LIST_URL, {"assignee": str(team.engineer.id)})
    unassigned = client_for(team.manager).get(LIST_URL, {"unassigned": "true"})

    assert by_assignee.data["count"] == 1
    assert unassigned.data["count"] == 1


def test_filter_overdue(client_for, team):
    from datetime import timedelta

    from django.utils import timezone

    TicketFactory(project=team.project, due_date=timezone.localdate() - timedelta(days=2))
    TicketFactory(project=team.project, due_date=timezone.localdate() + timedelta(days=2))

    response = client_for(team.manager).get(LIST_URL, {"overdue": "true"})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["is_overdue"] is True


def test_search_matches_key_and_title(client_for, team):
    target = TicketFactory(project=team.project, title="Payment gateway timeout")
    TicketFactory(project=team.project, title="Unrelated")

    by_title = client_for(team.manager).get(LIST_URL, {"search": "gateway"})
    by_key = client_for(team.manager).get(LIST_URL, {"search": target.key})

    assert by_title.data["count"] == 1
    assert by_key.data["count"] == 1
    assert by_key.data["results"][0]["key"] == target.key


def test_ordering_by_priority_is_semantic_not_alphabetical(client_for, team):
    low = TicketFactory(project=team.project, priority=Priority.LOW)
    critical = TicketFactory(project=team.project, priority=Priority.CRITICAL)
    medium = TicketFactory(project=team.project, priority=Priority.MEDIUM)

    descending = client_for(team.manager).get(LIST_URL, {"ordering": "-priority"})
    ascending = client_for(team.manager).get(LIST_URL, {"ordering": "priority"})

    assert [row["id"] for row in descending.data["results"]] == [str(critical.id), str(medium.id), str(low.id)]
    assert [row["id"] for row in ascending.data["results"]] == [str(low.id), str(medium.id), str(critical.id)]


# ---------------------------------------------------------------------------
# Collections and metadata
# ---------------------------------------------------------------------------
def test_my_assignments_returns_only_my_open_tickets(client_for, team):
    mine_open = TicketFactory(project=team.project, assignee=team.engineer, status=TicketStatus.IN_PROGRESS)
    TicketFactory(project=team.project, assignee=team.engineer, status=TicketStatus.CLOSED)
    TicketFactory(project=team.project, assignee=team.manager)

    response = client_for(team.engineer).get(f"{LIST_URL}my-assignments/")

    assert response.status_code == 200
    keys = [row["key"] for row in response.data["results"]]
    assert keys == [mine_open.key]


def test_my_assignments_can_include_finished_work(client_for, team):
    TicketFactory(project=team.project, assignee=team.engineer, status=TicketStatus.CLOSED)

    response = client_for(team.engineer).get(f"{LIST_URL}my-assignments/", {"include_done": "true"})

    assert response.data["count"] == 1


def test_choices_endpoint_exposes_enumerations(client_for, team):
    response = client_for(team.engineer).get(f"{LIST_URL}choices/")

    assert response.status_code == 200
    assert {row["value"] for row in response.data["statuses"]} == set(TicketStatus.values)
    assert {row["value"] for row in response.data["priorities"]} == set(Priority.values)
    assert len(response.data["types"]) == len(TicketType.values)
    assert len(response.data["severities"]) == len(Severity.values)


def test_detail_includes_counts_and_labels(client_for, team):
    from apps.tickets.models import Label, TicketLabel

    ticket = TicketFactory(project=team.project)
    label = Label.objects.create(project=team.project, name="regression")
    TicketLabel.objects.create(ticket=ticket, label=label)

    response = client_for(team.engineer).get(detail_url(ticket))

    assert response.status_code == 200
    assert response.data["labels"][0]["name"] == "regression"
    assert response.data["comment_count"] == 0
    assert response.data["attachment_count"] == 0