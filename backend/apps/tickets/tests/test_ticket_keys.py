"""Ticket key allocation tests (FR-3.2, FR-3.3, ADR-007).

The interesting cases are the failure modes: a counter that drifted, a collision, and (on
PostgreSQL only) genuine concurrent creation. The concurrency test is marked ``postgres`` and is
therefore **skipped** on SQLite — a green local run does not prove the row lock works, and pretending
otherwise would be the kind of claim this project is trying not to make.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connection, connections

from apps.tickets.models import Ticket, TicketKeySequence
from apps.tickets.services.keys import allocate_ticket_key, build_ticket_key
from apps.tickets.tests.factories import TicketFactory

pytestmark = pytest.mark.django_db


def test_first_key_of_a_project_is_number_one(team):
    key = allocate_ticket_key(team.project)

    assert key == f"{team.project.key}-1"
    assert TicketKeySequence.objects.get(project=team.project).last_number == 1


def test_keys_are_sequential_per_project(team):
    keys = [allocate_ticket_key(team.project) for _ in range(3)]

    assert keys == [f"{team.project.key}-{n}" for n in (1, 2, 3)]


def test_counters_are_independent_between_projects(team):
    from apps.projects.tests.factories import ProjectFactory

    other = ProjectFactory(key="OTHER")

    first = allocate_ticket_key(team.project)
    second = allocate_ticket_key(other)

    assert first == f"{team.project.key}-1"
    assert second == "OTHER-1"


def test_allocator_skips_a_key_that_already_exists(team):
    """Defends against a counter that drifted below the data (imports, restores, manual edits)."""
    existing = TicketFactory(project=team.project, title="Existing")  # takes <KEY>-1 via the allocator

    # Simulate drift: the counter forgets the existing row.
    sequence = TicketKeySequence.objects.get(project=team.project)
    sequence.last_number = 0
    sequence.save(update_fields=["last_number", "updated_at"])

    key = allocate_ticket_key(team.project)

    assert key == f"{team.project.key}-2"  # skipped the key that is already taken
    assert key != existing.key
    # The allocator only reserves a key; it does not create the row (that is create_ticket's job).
    assert Ticket.objects.filter(key=key).count() == 0


def test_retry_path_recovers_when_another_writer_took_the_key(team, monkeypatch):
    """Exercises ``create_with_allocated_key``'s retry without needing PostgreSQL.

    The race is injected deterministically. A committed row already holds the key the first
    allocation returns — exactly the state a concurrent writer leaves behind *after* committing, and
    the only state in which retrying is the right response. (A collision created inside our own
    savepoint would be rolled back with it, which is why the competing row is committed first.)
    """
    import apps.tickets.services.keys as keys_module

    winner = TicketFactory(project=team.project, title="Committed competitor")
    stolen_key = winner.key

    real_allocate = keys_module.allocate_ticket_key
    calls = {"count": 0}

    def fake_allocate(project):
        calls["count"] += 1
        if calls["count"] == 1:
            return stolen_key  # simulate losing the race
        return real_allocate(project)

    monkeypatch.setattr(keys_module, "allocate_ticket_key", fake_allocate)

    def build(key: str):
        return Ticket.objects.create(
            key=key,
            project=team.project,
            title="Retried",
            description="created after losing the race",
            reporter=team.reporter,
        )

    ticket = keys_module.create_with_allocated_key(project=team.project, build=build)

    assert calls["count"] == 2, "the service must retry exactly once after a lost race"
    assert ticket.key != stolen_key
    assert Ticket.objects.filter(project=team.project).count() == 2
    # The winner's row is untouched: a lost race must not damage the other writer's data.
    winner.refresh_from_db()
    assert winner.title == "Committed competitor"


def test_build_ticket_key_format():
    class FakeProject:
        key = "ENG"

    assert build_ticket_key(FakeProject(), 1042) == "ENG-1042"


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_creation_never_duplicates_a_key(team):
    """Real threads against PostgreSQL, where ``select_for_update`` actually locks.

    Skipped on SQLite: ``SELECT ... FOR UPDATE`` has no effect there, so the test would pass
    vacuously and give false confidence.
    """
    from apps.tickets.services.tickets import create_ticket

    workers = 8
    barrier = threading.Barrier(workers)
    keys: list[str] = []
    errors: list[BaseException] = []

    def create_one(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            ticket = create_ticket(
                actor=team.engineer,
                project=team.project,
                title=f"Concurrent {index}",
                description="created by a thread",
            )
            keys.append(ticket.key)
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=create_one, args=(i,)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors
    assert len(keys) == workers
    assert len(set(keys)) == workers, f"duplicate keys: {keys}"
    assert Ticket.objects.filter(project=team.project).count() == workers
    connection.close()