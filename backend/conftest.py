"""Shared pytest fixtures.

Design decisions worth knowing before adding fixtures here:

* **Real HTTP semantics where it matters.** Most tests use a session-authenticated client
  (``client_for(user)``), but CSRF and throttling tests use a client with
  ``enforce_csrf_checks=True`` so the protection is actually exercised rather than assumed.
* **No hidden state.** Fixtures create the *minimum* object graph and return it; tests that need a
  project build it explicitly, which keeps each test's preconditions readable.
* **PostgreSQL-only tests are skipped loudly.** ``-ra`` in addopts prints the skip reasons, so a
  green run on SQLite cannot be mistaken for "concurrency verified".
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.roles import SystemRole


def pytest_collection_modifyitems(config, items):
    """Skip PostgreSQL-only tests where the backend cannot provide row locking (ADR-008).

    These tests assert behaviour that only exists on PostgreSQL — most importantly real
    ``SELECT ... FOR UPDATE`` serialisation. On SQLite they are skipped rather than weakened,
    because a test that silently stops testing the lock is worse than no test.
    """
    from django.db import connection

    if connection.vendor == "postgresql":
        return

    skip_marker = pytest.mark.skip(reason="requires PostgreSQL (see ADR-008); run with Docker")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture
def api_client() -> APIClient:
    """Anonymous API client."""
    return APIClient()


@pytest.fixture
def client_for():
    """Factory returning an API client, optionally bound to a user session.

    Usage::

        client = client_for(user)                  # session-authenticated
        client = client_for(user, enforce_csrf=True)   # CSRF actually enforced
        client = client_for()                      # anonymous
    """

    def _make(user=None, *, enforce_csrf: bool = False) -> APIClient:
        client = APIClient(enforce_csrf_checks=enforce_csrf)
        if user is not None:
            client.force_login(user)
        return client

    return _make


@pytest.fixture
def admin_user(db):
    from apps.accounts.tests.factories import AdminUserFactory

    # AdminUserFactory sets is_staff=True as well, so the fixture matches what
    # ``change_system_role`` produces when it promotes somebody.
    return AdminUserFactory(full_name="Ada Admin", email="ada.admin@example.com")


@pytest.fixture
def manager_user(db):
    from apps.accounts.tests.factories import UserFactory

    return UserFactory(
        system_role=SystemRole.PROJECT_MANAGER, full_name="Mo Manager", email="mo.manager@example.com"
    )


@pytest.fixture
def engineer_user(db):
    from apps.accounts.tests.factories import UserFactory

    return UserFactory(system_role=SystemRole.ENGINEER, full_name="Eve Engineer", email="eve.engineer@example.com")


@pytest.fixture
def reporter_user(db):
    from apps.accounts.tests.factories import UserFactory

    return UserFactory(system_role=SystemRole.REPORTER, full_name="Rob Reporter", email="rob.reporter@example.com")


@pytest.fixture
def team(db):
    """A project with one actor per project role.

    Returned as a namespace rather than four separate fixtures: almost every ticket test needs the
    whole cast, and explicit construction of the membership graph is what makes the permission
    premise of each test visible.
    """
    from types import SimpleNamespace

    from apps.accounts.tests.factories import UserFactory
    from apps.projects.models import ProjectMembership, ProjectRole
    from apps.projects.tests.factories import ProjectFactory

    project = ProjectFactory()
    manager = project.owner  # ProjectFactory gives the owner an active MANAGER membership
    engineer = UserFactory(system_role=SystemRole.ENGINEER, full_name="Eve Engineer")
    reporter = UserFactory(system_role=SystemRole.REPORTER, full_name="Rob Reporter")
    outsider = UserFactory(system_role=SystemRole.ENGINEER, full_name="Otto Outsider")

    ProjectMembership.objects.create(project=project, user=engineer, role=ProjectRole.ENGINEER)
    ProjectMembership.objects.create(project=project, user=reporter, role=ProjectRole.REPORTER)

    return SimpleNamespace(
        project=project,
        manager=manager,
        engineer=engineer,
        reporter=reporter,
        outsider=outsider,
    )
