"""Ticket key allocation — the concurrency-safe part of ticket creation (ADR-007).

The problem: ``ENG-1042`` must never be handed out twice, even when two requests create a ticket in
the same project at the same instant.

Why not the two obvious approaches:

* ``MAX(number) + 1`` — two requests read the same maximum before either writes, so both produce the
  same key. Classic read-modify-write race.
* A database sequence per project — correct on PostgreSQL, but it requires DDL whenever a project is
  created, and it does not exist on SQLite, which we deliberately keep working for local development
  and for the default test run (ADR-008).

The protocol implemented here, in order of defence:

1. **A counter row per project, locked while it is incremented.** On PostgreSQL
   ``select_for_update()`` serialises concurrent allocators, so they queue instead of colliding.
2. **A uniqueness check before returning**, so a counter that drifted (for example after a manual
   data import) cannot hand out a key that already exists.
3. **The unique index on ``Ticket.key`` as the final authority.** If two allocations still race on a
   backend without row locking, the second ``INSERT`` fails; :func:`create_with_allocated_key`
   catches exactly that failure, verifies it really was a key collision, and retries with the next
   number. Each attempt runs in its own ``transaction.atomic()`` block, which is what turns the
   failure into a *savepoint* rollback instead of poisoning the surrounding transaction.

Consequence worth knowing: numbers are **gap-tolerant**. An attempt that rolls back still burns a
number, so key sequences may skip. That is accepted (assumption A-5) because a gap costs nothing,
while a duplicate identifier would corrupt references.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.tickets.models import Ticket, TicketKeySequence
from common.exceptions import InvariantViolation

logger = logging.getLogger(__name__)


def build_ticket_key(project, number: int) -> str:
    """``(project ENG, 1042) -> "ENG-1042"``. The only place the format is defined."""
    return f"{project.key}-{number}"


def _next_number(project) -> int:
    """Lock the project's counter, increment it, and return the new value."""
    sequence, _created = TicketKeySequence.objects.select_for_update().get_or_create(project=project)
    sequence.last_number += 1
    sequence.save(update_fields=["last_number", "updated_at"])
    return sequence.last_number


def allocate_ticket_key(project) -> str:
    """Return the next unused key for ``project``.

    Retries past any number whose key already exists, which keeps the counter and the data
    consistent even if a row was inserted by hand.
    """
    attempts = max(1, int(getattr(settings, "TICKET_KEY_MAX_RETRIES", 5)))

    with transaction.atomic():
        for _ in range(attempts):
            candidate = build_ticket_key(project, _next_number(project))
            if not Ticket.objects.filter(key=candidate).exists():
                return candidate
            logger.warning("Ticket key %s already exists; advancing the counter.", candidate)

    raise InvariantViolation(
        "Could not allocate a unique ticket key. Please retry.",
        code="ticket_key_allocation_failed",
        status_code=409,
    )


def create_with_allocated_key(*, project, build: Callable[[str], Ticket]) -> Ticket:
    """Create a ticket, allocating its key and surviving a lost race.

    ``build(key)`` must construct and save the ticket using the given key. It is called inside its
    own atomic block on every attempt, so a failed insert rolls back to a savepoint and the outer
    transaction stays usable — the detail that makes retrying possible at all.
    """
    attempts = max(1, int(getattr(settings, "TICKET_KEY_MAX_RETRIES", 5)))

    for attempt in range(1, attempts + 1):
        key = allocate_ticket_key(project)
        try:
            with transaction.atomic():
                return build(key)
        except IntegrityError:
            # Distinguish "somebody else took this key in the meantime" (retry) from any other
            # constraint violation (re-raise: it is a bug, not a race).
            if not Ticket.objects.filter(key=key).exists():
                raise
            logger.warning("Lost a ticket-key race for %s (attempt %s/%s).", key, attempt, attempts)

    raise InvariantViolation(
        "Could not allocate a unique ticket key. Please retry.",
        code="ticket_key_allocation_failed",
        status_code=409,
    )
