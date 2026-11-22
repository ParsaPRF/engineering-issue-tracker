"""People-directory endpoint tests (FR-2.5).

Why this file exists: the directory endpoint returned HTTP 500 in the running container stack
(`FieldError: Field User.profile cannot be both deferred and traversed using select_related`) while
the whole test suite was green — because no test ever called it. The membership tests added members
through the service, so the endpoint that the UI actually uses was untested. These tests exist to make
sure that cannot happen again.
"""

from __future__ import annotations

import pytest

from apps.accounts.roles import SystemRole
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

DIRECTORY_URL = "/api/v1/auth/users/directory/"


def test_project_manager_can_search_the_directory(client_for, manager_user):
    UserFactory(email="findme@example.com", full_name="Find Me")

    response = client_for(manager_user).get(DIRECTORY_URL, {"search": "findme"})

    assert response.status_code == 200, response.data
    assert [row["email"] for row in response.data] == ["findme@example.com"]


def test_admin_can_search_the_directory(client_for, admin_user):
    response = client_for(admin_user).get(DIRECTORY_URL)

    assert response.status_code == 200
    assert isinstance(response.data, list)


def test_directory_returns_only_public_fields(client_for, manager_user):
    UserFactory(email="public@example.com")

    row = client_for(manager_user).get(DIRECTORY_URL, {"search": "public"}).data[0]

    assert set(row) == {"id", "email", "full_name", "system_role", "is_active"}
    assert "password" not in row


def test_directory_matches_full_name(client_for, manager_user):
    UserFactory(email="someone@example.com", full_name="Zara Special")

    response = client_for(manager_user).get(DIRECTORY_URL, {"search": "Special"})

    assert [row["email"] for row in response.data] == ["someone@example.com"]


def test_directory_excludes_inactive_accounts(client_for, manager_user):
    UserFactory(email="gone@example.com", is_active=False)

    response = client_for(manager_user).get(DIRECTORY_URL, {"search": "gone"})

    assert response.data == []


def test_directory_is_bounded(client_for, manager_user):
    for index in range(30):
        UserFactory(email=f"bulk{index}@example.com")

    response = client_for(manager_user).get(DIRECTORY_URL, {"search": "bulk"})

    assert len(response.data) <= 20


@pytest.mark.security
@pytest.mark.parametrize("role", [SystemRole.ENGINEER, SystemRole.REPORTER])
def test_non_managers_cannot_browse_the_directory(client_for, role):
    user = UserFactory(system_role=role)

    response = client_for(user).get(DIRECTORY_URL)

    assert response.status_code == 403
    assert response.data["error"]["code"] == "permission_denied"


@pytest.mark.security
def test_anonymous_cannot_browse_the_directory(api_client):
    assert api_client.get(DIRECTORY_URL).status_code == 403