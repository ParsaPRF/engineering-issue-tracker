"""Assignment tests (FR-4.1 … FR-4.4).

Assignment has its own endpoint and its own rules (eligibility, self-assignment, audit wording), so it
gets its own test module rather than being folded into the ticket CRUD tests.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.tickets.models import TicketStatus
from apps.tickets.tests.factories import TicketFactory

pytestmark = pytest.mark.django_db


def assign_url(ticket) -> str:
    return f"/api/v1/tickets/{ticket.id}/assign/"


def error_code(response) -> str:
    return response.data["error"]["code"]


def test_manager_can_assign_an_unassigned_ticket(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter)

    response = client_for(team.manager).post(assign_url(ticket), {"assignee": str(team.engineer.id)}, format="json")

    assert response.status_code == 200, response.data
    ticket.refresh_from_db()
    assert ticket.assignee_id == team.engineer.id
    assert AuditEvent.objects.filter(action=AuditAction.TICKET_ASSIGNED, ticket=ticket).exists()


def test_reassignment_is_recorded_as_such(client_for, team):
    ticket = TicketFactory(project=team.project, assignee=team.manager)

    response = client_for(team.manager).post(assign_url(ticket), {"assignee": str(team.engineer.id)}, format="json")

    assert response.status_code == 200
    event = AuditEvent.objects.get(action=AuditAction.TICKET_REASSIGNED, ticket=ticket)
    assert event.metadata["from"] == str(team.manager.id)
    assert event.metadata["to"] == str(team.engineer.id)


def test_manager_can_unassign(client_for, team):
    ticket = TicketFactory(project=team.project, assignee=team.engineer)

    response = client_for(team.manager).post(assign_url(ticket), {"assignee": None}, format="json")

    assert response.status_code == 200
    ticket.refresh_from_db()
    assert ticket.assignee_id is None
    assert AuditEvent.objects.filter(action=AuditAction.TICKET_UNASSIGNED, ticket=ticket).exists()


def test_unassigning_an_unassigned_ticket_is_a_noop(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.manager).post(assign_url(ticket), {"assignee": None}, format="json")

    assert response.status_code == 200
    assert not AuditEvent.objects.filter(action=AuditAction.TICKET_UNASSIGNED, ticket=ticket).exists()


def test_engineer_can_self_assign_an_unassigned_ticket(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.engineer).post(assign_url(ticket), {"assignee": str(team.engineer.id)}, format="json")

    assert response.status_code == 200
    ticket.refresh_from_db()
    assert ticket.assignee_id == team.engineer.id


def test_engineer_cannot_steal_an_assigned_ticket(client_for, team):
    ticket = TicketFactory(project=team.project, assignee=team.manager)

    response = client_for(team.engineer).post(assign_url(ticket), {"assignee": str(team.engineer.id)}, format="json")

    assert response.status_code == 403
    ticket.refresh_from_db()
    assert ticket.assignee_id == team.manager.id


def test_engineer_cannot_assign_another_person(client_for, team):
    other_engineer = UserFactory()
    from apps.projects.models import ProjectMembership, ProjectRole

    ProjectMembership.objects.create(project=team.project, user=other_engineer, role=ProjectRole.ENGINEER)
    ticket = TicketFactory(project=team.project)

    response = client_for(team.engineer).post(assign_url(ticket), {"assignee": str(other_engineer.id)}, format="json")

    assert response.status_code == 403


def test_engineer_cannot_unassign_somebody_else(client_for, team):
    ticket = TicketFactory(project=team.project, assignee=team.manager)

    response = client_for(team.engineer).post(assign_url(ticket), {"assignee": None}, format="json")

    assert response.status_code == 403


def test_reporter_role_member_is_not_eligible(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.manager).post(assign_url(ticket), {"assignee": str(team.reporter.id)}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "ineligible_assignee"


def test_non_member_cannot_be_assigned(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.manager).post(assign_url(ticket), {"assignee": str(team.outsider.id)}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "ineligible_assignee"


def test_deactivated_engineer_cannot_be_assigned(client_for, team):
    ticket = TicketFactory(project=team.project)
    team.engineer.is_active = False
    team.engineer.save(update_fields=["is_active"])

    response = client_for(team.manager).post(assign_url(ticket), {"assignee": str(team.engineer.id)}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "ineligible_assignee"


@pytest.mark.security
def test_outsider_cannot_assign_anything(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.outsider).post(assign_url(ticket), {"assignee": str(team.engineer.id)}, format="json")

    assert response.status_code == 404  # the ticket is invisible, so its id must not confirm it exists


def test_assignment_does_not_change_status(client_for, team):
    ticket = TicketFactory(project=team.project, status=TicketStatus.TRIAGED)

    client_for(team.manager).post(assign_url(ticket), {"assignee": str(team.engineer.id)}, format="json")

    ticket.refresh_from_db()
    assert ticket.status == TicketStatus.TRIAGED


def test_unknown_user_is_a_404(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.manager).post(
        assign_url(ticket), {"assignee": "00000000-0000-0000-0000-000000000000"}, format="json"
    )

    assert response.status_code == 404