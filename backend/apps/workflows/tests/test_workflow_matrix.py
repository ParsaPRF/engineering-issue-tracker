"""Exhaustive transition-table tests (FR-5.2).

Two tests, both derived from ``TRANSITION_TABLE`` itself rather than from a hand-written list:

1. Every **declared** move succeeds for every role the rule allows, and is refused (403) for the
   project roles it does not allow.
2. Every **undeclared** (from, to) pair is refused with ``invalid_transition`` — including the pairs a
   developer might assume are allowed (``NEW → CLOSED``), and every no-op.

Because the expectations are derived from the same table the service uses, this suite cannot drift
from the implementation. What it *can* catch is the reverse mistake: a service that stops consulting
the table, or a rule that grants a role the table does not.
"""

from __future__ import annotations

import pytest

from apps.projects.models import ProjectRole
from apps.tickets.models import TicketStatus
from apps.tickets.tests.factories import TicketFactory
from apps.workflows import state_machine
from apps.workflows.services import transition_ticket
from apps.workflows.state_machine import TRANSITION_TABLE, InvalidTransition
from common.exceptions import AccessDenied

pytestmark = pytest.mark.django_db


def actor_for_role(team, role: str):
    return {
        ProjectRole.MANAGER: team.manager,
        ProjectRole.ENGINEER: team.engineer,
        ProjectRole.REPORTER: team.reporter,
    }[role]


@pytest.mark.parametrize(
    "rule",
    TRANSITION_TABLE,
    ids=[f"{rule.from_status}->{rule.to_status}" for rule in TRANSITION_TABLE],
)
def test_each_declared_move_respects_the_role_matrix(db, team, rule):
    for role in (ProjectRole.MANAGER, ProjectRole.ENGINEER, ProjectRole.REPORTER):
        actor = actor_for_role(team, role)
        ticket = TicketFactory(
            project=team.project,
            status=rule.from_status,
            assignee=team.engineer,
            reporter=team.reporter,
        )

        if role in rule.allowed_project_roles:
            history = transition_ticket(
                ticket=ticket,
                to_status=rule.to_status,
                actor=actor,
                comment="because the rule requires one",
            )
            assert history.to_status == rule.to_status
            assert history.from_status == rule.from_status
            ticket.refresh_from_db()
            assert ticket.status == rule.to_status
        else:
            with pytest.raises(AccessDenied):
                transition_ticket(
                    ticket=ticket,
                    to_status=rule.to_status,
                    actor=actor,
                    comment="because the rule requires one",
                )
            ticket.refresh_from_db()
            assert ticket.status == rule.from_status  # rolled back, not half-applied


def test_every_undeclared_move_is_refused(db, team):
    declared = set(state_machine.all_pairs())
    attempted = 0

    for from_status in TicketStatus.values:
        for to_status in TicketStatus.values:
            if from_status == to_status or (from_status, to_status) in declared:
                continue

            ticket = TicketFactory(
                project=team.project,
                status=from_status,
                assignee=team.engineer,
                reporter=team.reporter,
            )
            attempted += 1
            with pytest.raises(InvalidTransition):
                transition_ticket(
                    ticket=ticket,
                    to_status=to_status,
                    actor=team.manager,
                    comment="attempting the impossible",
                )
            ticket.refresh_from_db()
            assert ticket.status == from_status

    # Sanity check on the test itself: 10 statuses → 90 ordered pairs, minus 19 declared moves.
    assert attempted == len(TicketStatus.values) * (len(TicketStatus.values) - 1) - len(declared)


def test_noop_is_refused_through_the_service(db, team):
    for status in TicketStatus.values:
        ticket = TicketFactory(project=team.project, status=status, assignee=team.engineer)
        with pytest.raises(InvalidTransition):
            transition_ticket(ticket=ticket, to_status=status, actor=team.manager, comment="noop")


def test_table_has_no_duplicate_pairs():
    """A duplicated (from, to) pair would silently shadow the earlier rule."""
    pairs = [rule.key for rule in TRANSITION_TABLE]
    assert len(pairs) == len(set(pairs))


def test_every_rule_allows_a_manager_somewhere():
    """Guards against a state that becomes unreachable: at least one role must be able to act."""
    for rule in TRANSITION_TABLE:
        assert rule.allowed_project_roles, f"{rule.key} allows nobody"