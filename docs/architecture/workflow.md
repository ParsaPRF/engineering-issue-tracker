# Ticket Workflow

## 1. Why a state machine instead of a "status field"

A status field alone lets any client write any value: `NEW → CLOSED` in one request, with no
record of who did it or why. A ticket lifecycle is a **business process**: it has legal moves, an
actor who is allowed to make each move, preconditions, and side effects. Encoding that as an
explicit transition table (ADR-005) buys three things:

1. **Impossible states are unreachable.** `can_transition()` rejects anything not in the table.
2. **Permissions are expressed per move**, not per field — moving to `RESOLVED` is a different
   privilege from moving to `TRIAGED`.
3. **Every move is a fact with an actor and a time**, written to `TicketStatusHistory` in the same
   transaction as the status change, so history can never disagree with the current status.

Single source of truth: `apps/workflows/state_machine.py`. Nothing else decides what is legal.

## 2. States

| Status | Meaning | Terminal? |
| --- | --- | --- |
| `NEW` | Captured, not yet looked at. | no |
| `TRIAGED` | Accepted as real work, prioritised, ready to start. | no |
| `IN_PROGRESS` | Someone is actively working on it (requires an assignee). | no |
| `IN_REVIEW` | Code/fix ready, awaiting verification. | no |
| `RESOLVED` | Fix delivered; `resolved_at` is stamped. | no |
| `CLOSED` | Verified and finished. | no (reachable again via `REOPENED`) |
| `REOPENED` | Was resolved/closed and is live again. | no |
| `BLOCKED` | Cannot proceed (dependency, environment, missing info). | no |
| `REJECTED` | Will not be done; requires a written reason. | no |
| `DUPLICATE` | Tracked elsewhere; requires a written reference. | no |

`Priority` (how soon) and `Severity` (how bad technically) are deliberately independent: a
`CRITICAL` severity crash in an unused internal tool may be `LOW` priority, and a `LOWEST`
severity copy change on the pricing page may be `CRITICAL` priority.

## 3. Transition table

`R` = project role. `A` = the ticket's current assignee. Every move additionally requires the
actor to be an active member of the ticket's project, except system `ADMIN`.

| From | To | Who | Guards |
| --- | --- | --- | --- |
| NEW | TRIAGED | MANAGER, ADMIN | — |
| NEW | REJECTED | MANAGER, ADMIN | comment required |
| NEW | DUPLICATE | MANAGER, ADMIN | comment required |
| TRIAGED | IN_PROGRESS | MANAGER, ENGINEER, ADMIN, A | **assignee must be set** |
| TRIAGED | BLOCKED | MANAGER, ENGINEER, ADMIN, A | comment required |
| TRIAGED | REJECTED | MANAGER, ADMIN | comment required |
| TRIAGED | DUPLICATE | MANAGER, ADMIN | comment required |
| IN_PROGRESS | IN_REVIEW | MANAGER, ENGINEER, ADMIN, A | — |
| IN_PROGRESS | BLOCKED | MANAGER, ENGINEER, ADMIN, A | comment required |
| IN_PROGRESS | RESOLVED | MANAGER, ADMIN | assignee required, stamps `resolved_at` |
| IN_REVIEW | RESOLVED | MANAGER, ADMIN | assignee required, stamps `resolved_at` |
| IN_REVIEW | IN_PROGRESS | MANAGER, ENGINEER, ADMIN, A | — |
| BLOCKED | IN_PROGRESS | MANAGER, ENGINEER, ADMIN, A | assignee required |
| BLOCKED | REJECTED | MANAGER, ADMIN | comment required |
| BLOCKED | DUPLICATE | MANAGER, ADMIN | comment required |
| RESOLVED | CLOSED | MANAGER, ADMIN | stamps `closed_at` |
| RESOLVED | REOPENED | MANAGER, ENGINEER, REPORTER, ADMIN | comment required |
| CLOSED | REOPENED | MANAGER, REPORTER, ADMIN | comment required |
| REOPENED | IN_PROGRESS | MANAGER, ENGINEER, ADMIN, A | assignee required |
| REJECTED | REOPENED | MANAGER, ADMIN | comment required |
| DUPLICATE | REOPENED | MANAGER, ADMIN | comment required |

Notes and rationale:

* **Reporters can reopen but not close.** Closing is a delivery decision; reopening is a
  "this is not actually fixed" observation, which the person who reported it is best placed to
  make.
* **`IN_PROGRESS → RESOLVED` is a MANAGER/ADMIN shortcut** for cases verified out of band. The
  normal path is `IN_REVIEW`.
* **Why `REJECTED`/`DUPLICATE` are not terminal:** a ticket can be rejected for lack of
  information and later reopened when the information arrives. Keeping them non-terminal avoids
  forcing a duplicate ticket.
* **`BLOCKED` circles back to `IN_PROGRESS`** rather than to `TRIAGED`, because triage already
  happened.

## 4. Guards, side effects, and invariants

| Guard | Enforced in |
| --- | --- |
| Actor is an active project member (or global Admin) | `projects.permissions.can_transition_ticket` |
| Actor's project role is allowed for this move | `workflows.state_machine` + same permission function |
| `assignee` present before `IN_PROGRESS`/`RESOLVED` | `state_machine` guard list |
| Non-empty comment for `REJECTED`, `DUPLICATE`, `BLOCKED`, `REOPENED` | `state_machine` guard list |
| No-op move (`X → X`) | rejected as an invalid transition |

Side effects, all inside the same `transaction.atomic()` as the status write:

* `resolved_at` is stamped on entry to `RESOLVED` and cleared if the ticket is reopened.
* `closed_at` is stamped on entry to `CLOSED` and cleared on reopen.
* A `TicketStatusHistory` row is appended (`from_status`, `to_status`, `changed_by`, `comment`).
* One `AuditEvent` with action `ticket.status_changed` is recorded, referencing the history row id.
* A notification is queued for the reporter, the assignee, and the project's active managers
  (excluding the actor), with a dedup key of `ticket:<id>:status:<to_status>`.

## 5. Sequence diagram — a legal move and an illegal move

```
Actor              API                  workflows.service            DB
  |  POST /transitions/  |                      |                    |
  |--------------------->|  validate shape      |                    |
  |                      |--------------------->| BEGIN              |
  |                      |                      | SELECT ticket FOR UPDATE
  |                      |                      |------------------->|
  |                      |                      | can_transition?    |
  |                      |                      | can_transition_ticket?
  |                      |                      | guards (assignee/comment)
  |                      |                      | UPDATE ticket.status
  |                      |                      | INSERT status_history
  |                      |                      | INSERT audit_event
  |                      |                      | COMMIT             |
  |  200 updated ticket  |<---------------------|                    |
  |<---------------------|                      |                    |

Illegal: IN_PROGRESS -> TRIAGED
  service raises InvalidTransition (subclass of ValidationError)
  API maps it to 400 {"error": {"code": "invalid_transition", "detail": ...}}
  Transaction rolled back: no status change, no history, no audit row.
```

## 6. How a client discovers the legal moves

`GET /api/v1/workflows/transitions/?ticket=<uuid>` returns the transitions *this* actor may
currently perform on *this* ticket:

```json
{
  "current_status": "TRIAGED",
  "allowed": [
    {"to_status": "IN_PROGRESS", "requires_comment": false, "requires_assignee": true},
    {"to_status": "BLOCKED", "requires_comment": true, "requires_assignee": false}
  ]
}
```

The frontend renders buttons from this response instead of hard-coding the table — the UI cannot
drift from the backend rules, and a user never sees a button that would return `400`.
