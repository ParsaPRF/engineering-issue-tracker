"""Project API tests (FR-2.1 … FR-2.4, FR-2.7, FR-2.8).

Each test states its permission premise explicitly by constructing the membership it needs, so a
failure points at the rule rather than at a fixture.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.projects.models import Project, ProjectMembership, ProjectRole, ProjectStatus
from apps.projects.tests.factories import ProjectFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/projects/"


def detail_url(project) -> str:
    return f"/api/v1/projects/{project.id}/"


def error_code(response) -> str:
    return response.data["error"]["code"]


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def test_manager_can_create_project_and_becomes_its_manager(client_for, manager_user):
    client = client_for(manager_user)

    response = client.post(
        LIST_URL, {"key": "eng", "name": "Engineering", "description": "Core platform"}, format="json"
    )

    assert response.status_code == 201, response.data
    project = Project.objects.get(key="ENG")  # key normalised to upper case
    assert project.owner_id == manager_user.id
    assert project.status == ProjectStatus.ACTIVE
    # FR-2.1: the creator is added as an active manager, which is what makes the project manageable.
    membership = ProjectMembership.objects.get(project=project, user=manager_user)
    assert membership.role == ProjectRole.MANAGER and membership.is_active
    assert AuditEvent.objects.filter(action=AuditAction.PROJECT_CREATED, project=project).exists()


def test_engineer_and_reporter_cannot_create_projects(client_for, engineer_user, reporter_user):
    for user in (engineer_user, reporter_user):
        response = client_for(user).post(LIST_URL, {"key": "NOPE", "name": "Nope"}, format="json")
        assert response.status_code == 403, response.data
        assert error_code(response) == "permission_denied"
    assert not Project.objects.filter(key="NOPE").exists()


def test_duplicate_project_key_is_rejected_case_insensitively(client_for, manager_user):
    ProjectFactory(key="DUP")

    response = client_for(manager_user).post(LIST_URL, {"key": "dup", "name": "Dupe"}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "duplicate_project_key"
    assert Project.objects.filter(key__iexact="dup").count() == 1


def test_invalid_project_key_is_rejected(client_for, manager_user):
    response = client_for(manager_user).post(LIST_URL, {"key": "has space", "name": "Bad"}, format="json")

    assert response.status_code == 400
    assert "key" in response.data["error"]["fields"]


# ---------------------------------------------------------------------------
# Visibility (FR-2.7, NFR-1.3)
# ---------------------------------------------------------------------------
@pytest.mark.security
def test_project_list_only_contains_the_callers_projects(client_for):
    mine = ProjectFactory(key="MINE")
    outsider_project = ProjectFactory(key="THEIRS")
    member = UserFactory()
    ProjectMembership.objects.create(project=mine, user=member, role=ProjectRole.ENGINEER)

    response = client_for(member).get(LIST_URL)

    assert response.status_code == 200
    keys = [row["key"] for row in response.data["results"]]
    assert keys == ["MINE"]
    assert outsider_project.key not in keys


@pytest.mark.security
def test_admin_sees_every_project(client_for, admin_user):
    ProjectFactory(key="ONE")
    ProjectFactory(key="TWO")

    response = client_for(admin_user).get(LIST_URL)

    assert response.status_code == 200
    assert {row["key"] for row in response.data["results"]} == {"ONE", "TWO"}


@pytest.mark.security
def test_foreign_project_detail_returns_404_not_403(client_for):
    """Existence must not be confirmed to somebody who cannot see the project (NFR-1.3)."""
    project = ProjectFactory(key="SECRET")
    stranger = UserFactory()

    response = client_for(stranger).get(detail_url(project))

    assert response.status_code == 404
    assert error_code(response) == "not_found"


def test_project_detail_includes_counts(client_for):
    project = ProjectFactory(key="COUNT")
    owner = project.owner
    ProjectMembership.objects.create(project=project, user=UserFactory(), role=ProjectRole.ENGINEER)

    response = client_for(owner).get(detail_url(project))

    assert response.status_code == 200
    assert response.data["member_count"] == 2  # owner + engineer
    assert response.data["ticket_count"] == 0


# ---------------------------------------------------------------------------
# Update and lifecycle
# ---------------------------------------------------------------------------
def test_manager_can_update_project_fields(client_for):
    project = ProjectFactory(key="UPD", name="Before")
    client = client_for(project.owner)

    response = client.patch(detail_url(project), {"name": "After", "description": "Now described"}, format="json")

    assert response.status_code == 200
    project.refresh_from_db()
    assert project.name == "After"
    assert project.description == "Now described"
    audit = AuditEvent.objects.get(action=AuditAction.PROJECT_UPDATED, project=project)
    assert audit.metadata["changed"]["name"] == {"from": "Before", "to": "After"}


def test_project_key_cannot_be_changed(client_for):
    """``key`` is the prefix of every ticket key: changing it would invalidate existing tickets."""
    project = ProjectFactory(key="FIXED")
    client = client_for(project.owner)

    response = client.patch(detail_url(project), {"key": "MOVED", "name": "Still Fine"}, format="json")

    assert response.status_code == 200
    project.refresh_from_db()
    assert project.key == "FIXED"


def test_member_without_manager_role_cannot_update_project(client_for):
    project = ProjectFactory(key="RO")
    member = UserFactory()
    ProjectMembership.objects.create(project=project, user=member, role=ProjectRole.ENGINEER)

    response = client_for(member).patch(detail_url(project), {"name": "Nope"}, format="json")

    # The member may see the project (so not 404) but may not edit it.
    assert response.status_code == 403
    assert error_code(response) == "permission_denied"


def test_admin_can_update_any_project(client_for, admin_user):
    project = ProjectFactory(key="ADM")

    response = client_for(admin_user).patch(detail_url(project), {"name": "Admin Edit"}, format="json")

    assert response.status_code == 200
    project.refresh_from_db()
    assert project.name == "Admin Edit"


def test_archive_and_restore_project(client_for):
    project = ProjectFactory(key="ARCH")
    client = client_for(project.owner)

    archived = client.post(f"{detail_url(project)}archive/")
    assert archived.status_code == 200
    project.refresh_from_db()
    assert project.status == ProjectStatus.ARCHIVED
    assert project.archived_at is not None
    assert AuditEvent.objects.filter(action=AuditAction.PROJECT_ARCHIVED, project=project).exists()

    # Archiving twice is a business-rule violation, not a crash.
    assert client.post(f"{detail_url(project)}archive/").status_code == 400

    restored = client.post(f"{detail_url(project)}restore/")
    assert restored.status_code == 200
    project.refresh_from_db()
    assert project.status == ProjectStatus.ACTIVE
    assert project.archived_at is None


def test_project_has_no_delete_endpoint(client_for):
    """Nothing in the API can delete a project: the lifecycle is archive/restore (FR-2.4)."""
    project = ProjectFactory(key="NODEL")
    response = client_for(project.owner).delete(detail_url(project))
    assert response.status_code == 405
    assert Project.objects.filter(pk=project.pk).exists()


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def test_project_stats_endpoint_is_permission_scoped(client_for):
    project = ProjectFactory(key="STAT")
    stranger = UserFactory()

    ok = client_for(project.owner).get(f"{detail_url(project)}stats/")
    assert ok.status_code == 200
    assert ok.data["total_tickets"] == 0

    hidden = client_for(stranger).get(f"{detail_url(project)}stats/")
    assert hidden.status_code == 404


# ---------------------------------------------------------------------------
# Pagination and ordering
# ---------------------------------------------------------------------------
def test_project_list_is_paginated_with_a_capped_page_size(client_for, admin_user):
    for index in range(3):
        ProjectFactory(key=f"P{index}")

    response = client_for(admin_user).get(LIST_URL, {"page_size": 5000})

    assert response.status_code == 200
    assert response.data["page_size"] == 100  # max_page_size, not the requested 5000
    assert response.data["count"] == 3
    assert set(response.data.keys()) >= {"count", "next", "previous", "results", "total_pages"}


def test_unauthenticated_requests_are_rejected(api_client):
    assert api_client.get(LIST_URL).status_code == 403
