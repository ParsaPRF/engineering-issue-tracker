# Module Responsibilities

Each Django app is a bounded context. "Owns" means: only this module writes those tables.
Other modules may read them through selectors or act through services.

---

## `apps/accounts` — identity

**Owns:** `User`, `UserProfile`.
**Provides:** registration, login/logout (session), profile read/update, activation/deactivation,
system-role change (Admin only), `selectors.get_user_by_email`, `services.set_user_active`.
**Does not:** decide project-level access (that is `projects`).

Key files: `models/user.py`, `models/profile.py`, `api/views.py` (`RegisterView`, `SessionLoginView`,
`SessionLogoutView`, `MeView`), `services/users.py`, `selectors/users.py`, `managers.py`.

---

## `apps/projects` — projects, membership, components, and the permission kernel

**Owns:** `Project`, `ProjectMembership`, `Component`.
**Provides:** project CRUD + archive, membership management and role assignment, component CRUD,
project statistics (delegating ticket counts to `tickets.selectors`), and **all object-level
permission predicates** in `permissions.py`.
**Why permissions live here:** every other module needs "can this actor touch this project's
data?", so the rule set must sit below its consumers. It is pure functions over
`(actor, project/ticket)`, with no imports from `tickets`, which prevents cycles.

Key files: `permissions.py`, `services/projects.py`, `services/memberships.py`,
`selectors/projects.py`, `api/permissions.py`, `api/views.py`, `api/serializers.py`.

---

## `apps/tickets` — the core aggregate

**Owns:** `Ticket`, `TicketKeySequence`, `Label`, `TicketLabel`.
**Provides:** ticket CRUD (excluding status), assignment/reassignment, key generation,
filtering/search/ordering, ticket detail with related data.
**Does not:** change status (that is `workflows`), write comments/attachments (their modules),
decide permissions (queries the `projects` predicates).

Key files: `models/ticket.py`, `services/keys.py` (allocation), `services/tickets.py`
(create/update/assign), `selectors/tickets.py`, `api/views.py`, `filters.py`.

---

## `apps/workflows` — the lifecycle state machine

**Owns:** `TicketStatusHistory` (business timeline).
**Provides:** `state_machine.can_transition()`, `services.transition_ticket()`, the transition
catalogue endpoint (`GET /api/v1/workflows/transitions/`) so the UI knows which buttons to offer.
**Receives** the ticket as a parameter and imports `tickets.models` only for typing, so
`tickets` may import `workflows.services` without a cycle.

Key files: `state_machine.py` (the single source of truth for legal moves and guards),
`services.py`, `selectors.py`, `api/views.py`.

---

## `apps/comments` — collaboration on a ticket

**Owns:** `Comment`.
**Provides:** list/create/update/delete with edit/delete rules (author may edit for
`COMMENT_EDIT_WINDOW_MINUTES`; authors may soft-delete their own; Project Managers and Admins may
moderate-delete), and triggering notifications for new comments.

Key files: `models.py`, `services.py`, `selectors.py`, `api/views.py`, `api/permissions.py`.

---

## `apps/attachments` — private files

**Owns:** `Attachment`.
**Provides:** upload (validated), metadata listing, access-controlled download, delete
(uploader / PM / Admin), and storage cleanup on delete.

Key files: `models.py`, `validators.py` (allow-list, size, checksum), `services.py`,
`api/views.py`.

---

## `apps/notifications` — asynchronous fan-out

**Owns:** `Notification`.
**Provides:** `services.notify(event, recipients, subject)` (creates rows with a dedup key),
`tasks.send_notification` (Celery entry point), list/mark-read API, unread counter.
**Consumes:** it is called *by* other services; it never imports their services (avoids cycles).

Key files: `models.py`, `services.py`, `tasks.py`, `selectors.py`, `api/views.py`.

---

## `apps/audit` — append-only compliance trail

**Owns:** `AuditEvent`.
**Provides:** `services.record(actor, action, obj, metadata, ip)` and read-only query API.
**Rule:** other modules call `audit.services.record(...)`; nothing updates or deletes audit rows.

Key files: `models.py`, `services.py`, `selectors.py`, `api/views.py` (read-only), `actions.py`
(the action vocabulary).

---

## `apps/reports` — read-only aggregation

**Owns:** nothing (no tables).
**Provides:** dashboard endpoints: totals, open/resolved/blocked, by priority, by severity, by
project, per-engineer workload, recent activity. All queries are permission-scoped: a user only
sees aggregates over projects they belong to.

Key files: `selectors.py`, `api/views.py`.

---

## `common` — shared platform code

**Owns:** nothing (no models).
**Provides:** `models.py` (`UUIDModel`, `TimeStampedModel` abstract bases), `permissions.py`
(`IsAdmin`, `IsAuthenticatedAndActive`), `pagination.py`, `exceptions.py` (normalised error
envelope), `choices.py` (shared enum base), `uuid.py` (UUIDv7 helper), `utils.py` (client IP and
user agent for the audit trail), `views.py` (`/health/`).

**Rule:** if code in `common` needs to import a business module, it belongs in that module. This
is why test factories live in each app (`apps/<app>/tests/factories.py`) rather than in a shared
`common/testing/` package: a single factory module would have to import every app's models, which
is exactly the coupling the module boundaries exist to prevent. Tests import another app's factory
explicitly (`from apps.projects.tests.factories import ProjectFactory`), which also documents
cross-module usage.
