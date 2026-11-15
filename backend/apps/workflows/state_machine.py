"""The ticket lifecycle state machine — the single source of truth for legal moves (ADR-005).

Everything about "which status may follow which, for whom, and under what conditions" is declared in
one table below. Nothing else in the codebase decides it:

* the API reads the table to tell the frontend which buttons to show,
* the transition service reads it to validate a request,
* the tests iterate over it, so a new rule cannot be added without the matrix test noticing.

Why a table instead of ``if`` statements scattered through views and services: a lifecycle is a
*business process*, and a process is easier to review, diff and test when it is data. Adding a state
later means adding rows, not hunting for conditions.

Each rule can require:

* ``allowed_project_roles`` — which project roles may perform the move (global Admins bypass it),
* ``allow_assignee`` — the ticket's current assignee may also perform it,
* ``requires_comment`` — the actor must explain (rejections, blocks, duplicates, reopens),
* ``requires_assignee`` — work cannot start or finish with nobody owning it,
* stamping/clearing of ``resolved_at`` / ``closed_at``, which are derived facts about the lifecycle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from apps.projects.models import ProjectRole
from apps.tickets.models import TicketStatus
from common.exceptions import InvariantViolation

MANAGER = ProjectRole.MANAGER
ENGINEER = ProjectRole.ENGINEER
REPORTER = ProjectRole.REPORTER


class InvalidTransition(InvariantViolation):
    """The requested move is not in the table (or is a no-op)."""

    code = "invalid_transition"
    status_code = 400
    default_message = "This status change is not allowed from the ticket's current status."


class TransitionNotPermitted(InvariantViolation):
    """The move exists, but this actor's role does not permit it."""

    code = "transition_not_permitted"
    status_code = 403
    default_message = "Your project role does not allow this status change."


@dataclass(frozen=True, slots=True)
class TransitionRule:
    """One legal move in the lifecycle."""

    from_status: str
    to_status: str
    allowed_project_roles: frozenset[str] = field(default_factory=frozenset)
    allow_assignee: bool = False
    requires_comment: bool = False
    requires_assignee: bool = False
    stamps_resolved_at: bool = False
    clears_resolved_at: bool = False
    stamps_closed_at: bool = False
    clears_closed_at: bool = False
    #: Human-readable explanation of the business intent, surfaced by the transitions endpoint so
    #: the UI can label the button meaningfully ("Reject with a reason").
    label: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.from_status, self.to_status)


#: The lifecycle. Read this top to bottom as the process: capture → triage → work → review → resolve
#: → close, with blocked/rejected/duplicate as documented detours and reopen paths back in.
TRANSITION_TABLE: tuple[TransitionRule, ...] = (
    # --- Triage -------------------------------------------------------------
    TransitionRule(
        TicketStatus.NEW,
        TicketStatus.TRIAGED,
        allowed_project_roles=frozenset({MANAGER}),
        label="Accept for work",
    ),
    TransitionRule(
        TicketStatus.NEW,
        TicketStatus.REJECTED,
        allowed_project_roles=frozenset({MANAGER}),
        requires_comment=True,
        label="Reject with a reason",
    ),
    TransitionRule(
        TicketStatus.NEW,
        TicketStatus.DUPLICATE,
        allowed_project_roles=frozenset({MANAGER}),
        requires_comment=True,
        label="Mark as duplicate",
    ),
    # --- Start work ---------------------------------------------------------
    TransitionRule(
        TicketStatus.TRIAGED,
        TicketStatus.IN_PROGRESS,
        allowed_project_roles=frozenset({MANAGER, ENGINEER}),
        allow_assignee=True,
        requires_assignee=True,
        label="Start work",
    ),
    TransitionRule(
        TicketStatus.REOPENED,
        TicketStatus.IN_PROGRESS,
        allowed_project_roles=frozenset({MANAGER, ENGINEER}),
        allow_assignee=True,
        requires_assignee=True,
        label="Restart work",
    ),
    TransitionRule(
        TicketStatus.BLOCKED,
        TicketStatus.IN_PROGRESS,
        allowed_project_roles=frozenset({MANAGER, ENGINEER}),
        allow_assignee=True,
        requires_assignee=True,
        label="Unblock and continue",
    ),
    # --- Blocking -----------------------------------------------------------
    TransitionRule(
        TicketStatus.TRIAGED,
        TicketStatus.BLOCKED,
        allowed_project_roles=frozenset({MANAGER, ENGINEER}),
        allow_assignee=True,
        requires_comment=True,
        label="Block",
    ),
    TransitionRule(
        TicketStatus.IN_PROGRESS,
        TicketStatus.BLOCKED,
        allowed_project_roles=frozenset({MANAGER, ENGINEER}),
        allow_assignee=True,
        requires_comment=True,
        label="Block",
    ),
    TransitionRule(
        TicketStatus.BLOCKED,
        TicketStatus.REJECTED,
        allowed_project_roles=frozenset({MANAGER}),
        requires_comment=True,
        label="Reject while blocked",
    ),
    TransitionRule(
        TicketStatus.BLOCKED,
        TicketStatus.DUPLICATE,
        allowed_project_roles=frozenset({MANAGER}),
        requires_comment=True,
        label="Mark duplicate while blocked",
    ),
    # --- Review -------------------------------------------------------------
    TransitionRule(
        TicketStatus.IN_PROGRESS,
        TicketStatus.IN_REVIEW,
        allowed_project_roles=frozenset({MANAGER, ENGINEER}),
        allow_assignee=True,
        label="Send to review",
    ),
    TransitionRule(
        TicketStatus.IN_REVIEW,
        TicketStatus.IN_PROGRESS,
        allowed_project_roles=frozenset({MANAGER, ENGINEER}),
        allow_assignee=True,
        label="Request changes",
    ),
    # --- Resolution ---------------------------------------------------------
    TransitionRule(
        TicketStatus.IN_REVIEW,
        TicketStatus.RESOLVED,
        allowed_project_roles=frozenset({MANAGER}),
        requires_assignee=True,
        stamps_resolved_at=True,
        label="Verify and resolve",
    ),
    TransitionRule(
        # Manager/Admin shortcut for work verified out of band; the normal path is IN_REVIEW.
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
        allowed_project_roles=frozenset({MANAGER}),
        requires_assignee=True,
        stamps_resolved_at=True,
        label="Resolve directly",
    ),
    TransitionRule(
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
        allowed_project_roles=frozenset({MANAGER}),
        requires_assignee=True,
        stamps_closed_at=True,
        label="Close",
    ),
    # --- Reopen paths -------------------------------------------------------
    TransitionRule(
        TicketStatus.RESOLVED,
        TicketStatus.REOPENED,
        # Reporters may reopen: "it is not actually fixed" is an observation they are best placed to
        # make. They cannot close, because closing is a delivery decision.
        allowed_project_roles=frozenset({MANAGER, ENGINEER, REPORTER}),
        requires_comment=True,
        clears_resolved_at=True,
        label="Reopen",
    ),
    TransitionRule(
        TicketStatus.CLOSED,
        TicketStatus.REOPENED,
        allowed_project_roles=frozenset({MANAGER, REPORTER}),
        requires_comment=True,
        clears_resolved_at=True,
        clears_closed_at=True,
        label="Reopen",
    ),
    TransitionRule(
        TicketStatus.REJECTED,
        TicketStatus.REOPENED,
        allowed_project_roles=frozenset({MANAGER}),
        requires_comment=True,
        label="Reconsider",
    ),
    TransitionRule(
        TicketStatus.DUPLICATE,
        TicketStatus.REOPENED,
        allowed_project_roles=frozenset({MANAGER}),
        requires_comment=True,
        label="Un-duplicate",
    ),
)

#: Fast lookup built once at import time.
_RULES_BY_KEY: dict[tuple[str, str], TransitionRule] = {rule.key: rule for rule in TRANSITION_TABLE}


def get_rule(from_status: str, to_status: str) -> TransitionRule | None:
    """Return the rule for this move, or ``None`` when the move is not allowed at all."""
    return _RULES_BY_KEY.get((from_status, to_status))


def rules_from(status: str) -> list[TransitionRule]:
    """All declared rules leaving ``status``, regardless of who is asking."""
    return [rule for rule in TRANSITION_TABLE if rule.from_status == status]


def is_noop(from_status: str, to_status: str) -> bool:
    return from_status == to_status


def guard_failures(rule: TransitionRule, ticket) -> list[str]:
    """Preconditions that the ticket itself does not satisfy right now.

    Returned as a list (empty means "satisfied") so the transitions endpoint can explain *why* a move
    is currently unavailable instead of silently hiding it.
    """
    failures: list[str] = []
    if rule.requires_assignee and not getattr(ticket, "assignee_id", None):
        failures.append("assignee_required")
    return failures


def validate_comment(rule: TransitionRule, comment: str) -> str:
    """Normalise the transition comment and enforce ``requires_comment``."""
    text = (comment or "").strip()
    if rule.requires_comment and not text:
        raise InvariantViolation(
            "This status change requires an explanatory comment.",
            code="comment_required",
            fields={"comment": ["A comment is required for this transition."]},
        )
    return text


def describe(rule: TransitionRule) -> dict:
    """Serialisable description used by the "what can I do next?" endpoint."""
    return {
        "from_status": rule.from_status,
        "to_status": rule.to_status,
        "label": rule.label or rule.to_status.replace("_", " ").title(),
        "requires_comment": rule.requires_comment,
        "requires_assignee": rule.requires_assignee,
    }


def all_pairs() -> Sequence[tuple[str, str]]:
    """Every declared move, for tests and documentation generation."""
    return tuple(rule.key for rule in TRANSITION_TABLE)