"""Membership and component tests (FR-2.5, FR-2.6).

The interesting cases here are the invariants, not the happy path: a project must always keep a
manager, the owner cannot be removed or demoted, and removing a member must not leave open tickets
assigned to somebody who can no longer open them.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.projects.models import Component, ProjectMembership, ProjectRole
from apps.projects.tests.factories import ComponentFactory, ProjectFactory

pytestmark = pytest.mark.django_db


def members_url(project) -> str:
    return f"/api/v1/projects/{project.id}/members/"


def member_url(project, membership) -> str:
    return f"/api/v1/projects/{project.id}/members/{membership.id}/"


def components_url(project) -> str:
    return f"/api/v1/projects/{project.id}/components/"


def error_code(response) -> str:
    return response.data["error"]["code"]


# ---------------------------------------------------------------------------
# Adding members
# ---------------------------------------------------------------------------
def test_manager_can_add_member_with_a_project_role(client_for):
    project = ProjectFactory(key="ADD")
    newcomer = UserFactory()

    response = client_for(project.owner).post(
        members_url(project), {"user": str(newcomer.id), "role": ProjectRole.ENGINEER}, format="json"
    )

    assert response.status_code == 201, response.data
    membership = ProjectMembership.objects.get(project=project, user=newcomer)
    assert membership.role == ProjectRole.ENGINEER and membership.is_active
    assert AuditEvent.objects.filter(action=AuditAction.MEMBERSHIP_ADDED, project=project).exists()


def test_non_manager_cannot_add_members(client_for):
    project = ProjectFactory(key="NOPE")
    member = UserFactory()
    ProjectMembership.objects.create(project=project, user=member, role=ProjectRole.ENGINEER)
    target = UserFactory()

    response = client_for(member).post(
        members_url(project), {"user": str(target.id), "role": ProjectRole.REPORTER}, format="json"
    )

    assert response.status_code == 403
    assert not ProjectMembership.objects.filter(project=project, user=target).exists()


def test_deactivated_user_cannot_be_added(client_for):
    project = ProjectFactory(key="INACT")
    deactivated = UserFactory(is_active=False)

    response = client_for(project.owner).post(
        members_url(project), {"user": str(deactivated.id), "role": ProjectRole.ENGINEER}, format="json"
    )

    assert response.status_code == 400
    assert error_code(response) == "inactive_user"


def test_re_adding_a_removed_member_reactivates_the_row(client_for):
    project = ProjectFactory(key="REACT")
    member = UserFactory()
    membership = ProjectMembership.objects.create(
        project=project, user=member, role=ProjectRole.REPORTER, is_active=False
    )
    client = client_for(project.owner)

    response = client.post(
        members_url(project), {"user": str(member.id), "role": ProjectRole.ENGINEER}, format="json"
    )

    assert response.status_code == 200
    membership.refresh_from_db()
    assert membership.is_active is True
    assert membership.role == ProjectRole.ENGINEER
    # The row is reused, not duplicated: the unique constraint on (project, user) guarantees it.
    assert ProjectMembership.objects.filter(project=project, user=member).count() == 1
    assert AuditEvent.objects.filter(action=AuditAction.MEMBERSHIP_REACTIVATED, project=project).exists()


def test_adding_an_unknown_user_is_a_404(client_for):
    project = ProjectFactory(key="GHOST")

    response = client_for(project.owner).post(
        members_url(project), {"user": "00000000-0000-0000-0000-000000000000", "role": ProjectRole.ENGINEER},
        format="json",
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Role changes and removal
# ---------------------------------------------------------------------------
def test_manager_can_change_a_member_role(client_for):
    project = ProjectFactory(key="ROLE")
    member = UserFactory()
    membership = ProjectMembership.objects.create(project=project, user=member, role=ProjectRole.REPORTER)

    response = client_for(project.owner).patch(
        member_url(project, membership), {"role": ProjectRole.ENGINEER}, format="json"
    )

    assert response.status_code == 200
    membership.refresh_from_db()
    assert membership.role == ProjectRole.ENGINEER
    assert AuditEvent.objects.filter(action=AuditAction.MEMBERSHIP_ROLE_CHANGED, project=project).exists()


def test_the_last_manager_cannot_be_demoted(client_for):
    """Otherwise nobody could administer the project — an unrecoverable state through the API."""
    project = ProjectFactory(key="LAST")
    owner_membership = ProjectMembership.objects.get(project=project, user=project.owner)

    response = client_for(project.owner).patch(
        member_url(project, owner_membership), {"role": ProjectRole.ENGINEER}, format="json"
    )

    assert response.status_code == 400
    assert error_code(response) in {"last_manager", "owner_must_be_manager"}
    owner_membership.refresh_from_db()
    assert owner_membership.role == ProjectRole.MANAGER


def test_a_second_manager_makes_demotion_possible(client_for):
    project = ProjectFactory(key="TWO")
    second = UserFactory()
    second_membership = ProjectMembership.objects.create(
        project=project, user=second, role=ProjectRole.MANAGER
    )
    client = client_for(project.owner)

    response = client.patch(member_url(project, second_membership), {"role": ProjectRole.ENGINEER}, format="json")

    assert response.status_code == 200  # the owner remains a manager, so the invariant holds


def test_owner_cannot_be_removed(client_for):
    project = ProjectFactory(key="OWNER")
    owner_membership = ProjectMembership.objects.get(project=project, user=project.owner)

    response = client_for(project.owner).delete(member_url(project, owner_membership))

    assert response.status_code == 400
    assert error_code(response) == "owner_cannot_be_removed"


def test_removing_a_member_clears_their_open_assignments(client_for):
    """Access and workload must not drift apart (see memberships.remove_member)."""
    from apps.tickets.tests.factories import TicketFactory

    project = ProjectFactory(key="CLEAR")
    engineer = UserFactory()
    membership = ProjectMembership.objects.create(project=project, user=engineer, role=ProjectRole.ENGINEER)
    ticket = TicketFactory(project=project, assignee=engineer)

    response = client_for(project.owner).delete(member_url(project, membership))

    assert response.status_code == 204
    ticket.refresh_from_db()
    assert ticket.assignee_id is None
    membership.refresh_from_db()
    assert membership.is_active is False


def test_removing_a_member_is_idempotent_aware(client_for):
    project = ProjectFactory(key="TWICE")
    member = UserFactory()
    membership = ProjectMembership.objects.create(
        project=project, user=member, role=ProjectRole.ENGINEER, is_active=False
    )
    client = client_for(project.owner)

    response = client.delete(member_url(project, membership))

    assert response.status_code == 400
    assert error_code(response) == "already_inactive"


def test_membership_from_another_project_is_not_reachable(client_for):
    """Guards against IDOR: a membership id from project B must not be manageable through project A."""
    project_a = ProjectFactory(key="AAA")
    project_b = ProjectFactory(key="BBB")
    foreign_membership = ProjectMembership.objects.create(
        project=project_b, user=UserFactory(), role=ProjectRole.ENGINEER
    )

    response = client_for(project_a.owner).patch(
        member_url(project_a, foreign_membership), {"role": ProjectRole.MANAGER}, format="json"
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
def test_manager_can_create_component(client_for):
    project = ProjectFactory(key="COMP")
    lead = UserFactory()
    ProjectMembership.objects.create(project=project, user=lead, role=ProjectRole.ENGINEER)

    response = client_for(project.owner).post(
        components_url(project), {"name": "Billing API", "description": "Payments", "lead": str(lead.id)}, format="json"
    )

    assert response.status_code == 201, response.data
    component = Component.objects.get(project=project, name="Billing API")
    assert component.lead_id == lead.id
    assert AuditEvent.objects.filter(action=AuditAction.COMPONENT_CREATED, project=project).exists()


def test_component_name_is_unique_inside_a_project(client_for):
    project = ProjectFactory(key="UNIQ")
    ComponentFactory(project=project, name="Mobile App")

    response = client_for(project.owner).post(components_url(project), {"name": "mobile app"}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "duplicate_component_name"


def test_component_lead_must_be_a_project_member(client_for):
    project = ProjectFactory(key="LEAD")
    outsider = UserFactory()

    response = client_for(project.owner).post(
        components_url(project), {"name": "Orphan", "lead": str(outsider.id)}, format="json"
    )

    assert response.status_code == 400
    assert error_code(response) == "ineligible_lead"


def test_component_can_be_deactivated_without_losing_tickets(client_for):
    project = ProjectFactory(key="DEACT")
    component = ComponentFactory(project=project, name="Legacy")
    from apps.tickets.tests.factories import TicketFactory

    ticket = TicketFactory(project=project, component=component)

    response = client_for(project.owner).post(f"/api/v1/components/{component.id}/deactivate/")

    assert response.status_code == 200
    component.refresh_from_db()
    assert component.is_active is False
    ticket.refresh_from_db()
    assert ticket.component_id == component.id  # history preserved
    assert AuditEvent.objects.filter(action=AuditAction.COMPONENT_DEACTIVATED).exists()


def test_stranger_cannot_read_components_of_a_foreign_project(client_for):
    project = ProjectFactory(key="HIDDEN")
    ComponentFactory(project=project, name="Internal")

    response = client_for(UserFactory()).get(components_url(project))

    assert response.status_code == 404


def test_engineer_cannot_manage_components(client_for):
    project = ProjectFactory(key="ENGC")
    engineer = UserFactory()
    ProjectMembership.objects.create(project=project, user=engineer, role=ProjectRole.ENGINEER)

    response = client_for(engineer).post(components_url(project), {"name": "Nope"}, format="json")

    assert response.status_code == 403
