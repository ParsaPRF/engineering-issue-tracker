"""Reporting tests (FR-9.1 … FR-9.5).

The hard requirement is the last one: aggregates must never include tickets from projects the caller
cannot see. A dashboard that leaks another team's numbers is a data breach with pretty colours, so
scoping gets its own tests.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.audit.actions import AuditAction
from apps.audit.services import record
from apps.projects.models import ProjectMembership, ProjectRole
from apps.projects.tests.factories import ProjectFactory
from apps.tickets.models import TicketStatus
from apps.tickets.tests.factories import TicketFactory

pytestmark = pytest.mark.django_db


def test_dashboard_totals_and_breakdowns(client_for, team):
    TicketFactory(project=team.project, status=TicketStatus.NEW, severity="CRITICAL")
    TicketFactory(project=team.project, status=TicketStatus.RESOLVED)
    TicketFactory(project=team.project, status=TicketStatus.BLOCKED)

    response = client_for(team.engineer).get("/api/v1/reports/dashboard/")

    assert response.status_code == 200, response.data
    totals = response.data["totals"]
    assert totals["total_tickets"] == 3
    assert totals["open_tickets"] == 2  # NEW + BLOCKED are open
    assert totals["resolved_tickets"] == 1
    assert totals["blocked_tickets"] == 1
    # Zeroes are filled in so the UI can render every bar.
    assert response.data["by_severity"]["CRITICAL"] == 1
    assert response.data["by_severity"]["TRIVIAL"] == 0
    assert set(response.data["by_status"]) == set(TicketStatus.values)


@pytest.mark.security
def test_dashboard_never_counts_invisible_projects(client_for, team):
    TicketFactory(project=team.project)
    other_project = ProjectFactory(key="HIDDEN")
    TicketFactory(project=other_project)

    response = client_for(team.engineer).get("/api/v1/reports/dashboard/")

    assert response.data["totals"]["total_tickets"] == 1
    assert [row["project_key"] for row in response.data["by_project"]] == [team.project.key]
    assert response.data["project_count"] == 1


def test_dashboard_can_be_filtered_by_project(client_for, team):
    second = ProjectFactory(key="SECOND")
    ProjectMembership.objects.create(project=second, user=team.engineer, role=ProjectRole.ENGINEER)
    TicketFactory(project=team.project)
    TicketFactory(project=second)

    response = client_for(team.engineer).get(
        "/api/v1/reports/dashboard/", {"project": str(second.id)}
    )

    assert response.data["totals"]["total_tickets"] == 1


def test_dashboard_ignores_project_ids_the_caller_cannot_see(client_for, team):
    """Passing a foreign project id can only narrow the result set, never widen it."""
    foreign = ProjectFactory(key="FOREIGN")
    TicketFactory(project=team.project)
    TicketFactory(project=foreign)

    response = client_for(team.engineer).get(
        "/api/v1/reports/dashboard/", {"project": str(foreign.id)}
    )

    assert response.data["totals"]["total_tickets"] == 0


def test_workload_includes_engineers_with_no_tickets(client_for, team):
    TicketFactory(project=team.project, assignee=team.engineer, status=TicketStatus.IN_PROGRESS)

    response = client_for(team.manager).get("/api/v1/reports/workload/")

    assert response.status_code == 200
    by_email = {row["email"]: row for row in response.data["results"]}
    assert by_email[team.engineer.email]["open_tickets"] == 1
    # A manager with no tickets still appears: "who is free?" matters as much as "who is loaded?".
    assert team.manager.email in by_email
    assert by_email[team.manager.email]["open_tickets"] == 0


def test_my_workload(client_for, team):
    TicketFactory(project=team.project, assignee=team.engineer, status=TicketStatus.IN_PROGRESS)
    TicketFactory(project=team.project, assignee=team.engineer, status=TicketStatus.CLOSED)

    response = client_for(team.engineer).get("/api/v1/reports/my-workload/")

    assert response.status_code == 200
    assert response.data["open_tickets"] == 1
    assert response.data["total_tickets"] == 2


def test_recent_activity_is_scoped_to_visible_projects(client_for, team):
    ticket = TicketFactory(project=team.project)
    record(action=AuditAction.TICKET_UPDATED, actor=team.manager, obj=ticket, ticket=ticket, project=team.project)

    other_project = ProjectFactory(key="OTHER")
    other_ticket = TicketFactory(project=other_project)
    record(
        action=AuditAction.TICKET_UPDATED,
        actor=other_project.owner,
        obj=other_ticket,
        ticket=other_ticket,
        project=other_project,
    )

    response = client_for(team.engineer).get("/api/v1/reports/recent-activity/")

    assert response.status_code == 200
    project_keys = {row["project_key"] for row in response.data["results"]}
    assert project_keys == {team.project.key}


def test_recent_activity_limit_is_bounded(client_for, admin_user):
    from apps.audit.actions import AuditAction

    for _ in range(5):
        record(action=AuditAction.USER_LOGGED_IN, actor=admin_user, obj=admin_user)

    response = client_for(admin_user).get("/api/v1/reports/recent-activity/", {"limit": 2})

    assert len(response.data["results"]) == 2


def test_project_statistics_endpoint(client_for, team):
    TicketFactory(project=team.project, status=TicketStatus.NEW, priority="CRITICAL")
    TicketFactory(project=team.project, status=TicketStatus.RESOLVED)

    response = client_for(team.manager).get(f"/api/v1/projects/{team.project.id}/stats/")

    assert response.status_code == 200
    assert response.data["total_tickets"] == 2
    assert response.data["by_priority"]["CRITICAL"] == 1
    assert response.data["done_tickets"] == 1


def test_project_options_list_is_scoped(client_for, team):
    ProjectFactory(key="ELSEWHERE")

    response = client_for(team.engineer).get("/api/v1/reports/projects/")

    assert response.status_code == 200
    assert [row["key"] for row in response.data["results"]] == [team.project.key]


@pytest.mark.security
def test_a_user_without_memberships_sees_empty_reports(client_for):
    loner = UserFactory()

    response = client_for(loner).get("/api/v1/reports/dashboard/")

    assert response.status_code == 200
    assert response.data["totals"]["total_tickets"] == 0
    assert response.data["project_count"] == 0