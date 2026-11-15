# Architecture Decision Records

Format: **Context â†’ Options â†’ Decision â†’ Consequences**. Only decisions that were genuinely
uncertain or that constrain future work are recorded. Dates are the date of the decision.

---

## ADR-001 â€” Modular monolith instead of microservices

**Context.** The product has ~9 business capabilities with heavy cross-entity rules (a ticket
transition touches ticket, workflow, membership, audit and notification).

**Options.** (a) Microservices per module; (b) layered monolith; (c) modular monolith with
strict in-process module boundaries.

**Decision.** (c). One Django project, one database, one deployment unit, but each bounded
context is a separate Django app with its own models/services/selectors/api/tests.

**Consequences.** Distributed-transaction problems disappear; refactoring across modules is
cheap; a module can later be extracted if a real scaling or ownership pressure appears.
Cost: boundaries are enforced by discipline and review, not by the network.

---

## ADR-002 â€” Django 5.2 LTS on Python 3.14

**Context.** The host provides Python 3.14.2. Django 6.1.3 exists but is a fresh feature
release.

**Options.** Django 6.1 (newest), Django 5.2 LTS.

**Decision.** Django 5.2 LTS. Per the official FAQ table, Python 3.14 support was added in
Django 5.2.8; 5.2 is an LTS with security support into 2028.

**Consequences.** Stable, long-supported base and an officially supported interpreter pair.
We forgo 6.x-only features (none are needed).

---

## ADR-003 â€” Session authentication for the browser client, not JWT in browser storage

**Context.** The API is consumed by our own SPA served from the same site (Nginx in production,
Vite proxy in development). There is no third-party or mobile client in v1.

**Options.**
* JWT access token in memory + refresh token in `localStorage`: survives reloads, but any XSS
  escalates to full account takeover because the refresh token is readable by JavaScript; also
  needs revocation infrastructure (blacklist) to support logout-everywhere.
* JWT refresh token in an `HttpOnly` cookie: fixes token theft, but then CSRF protection is
  needed anyway, and we carry JWT complexity for no client that needs it.
* Django session cookie (`HttpOnly`, `SameSite=Lax`) + CSRF token header: battle-tested,
  server-side revocation by deleting the session row, no token in JS-accessible storage.

**Decision.** Session authentication as the default for the SPA. `SessionAuthentication` in DRF
enforces CSRF on unsafe methods; the frontend sends `X-CSRFToken`. CORS in development uses
explicit origin allow-list with credentials enabled, and `CORS_ALLOW_CREDENTIALS = True`.

**Consequences.** No refresh tokens anywhere, so the "never store long-lived refresh tokens in
browser storage" requirement is satisfied by construction. Cost: not suitable for non-browser
clients; if a mobile client appears, add `djangorestframework-simplejwt` as an *additional*
authentication class â€” the permission layer is unchanged because permissions depend on
`request.user`, not on the token format.

---

## ADR-004 â€” Service layer for writes, selectors for reads

**Context.** Django invites "fat serializers" and "fat views". The workflow rules must be
reusable from the API, Celery tasks, management commands and tests.

**Decision.** Writes go through `apps/<module>/services/*.py` functions that own transaction
boundaries; reads go through `apps/<module>/selectors/*.py` functions that return querysets.
Serializers validate *shape*; services validate *business rules*.

**Consequences.** Business rules have exactly one home and are testable without HTTP. Cost:
slightly more files and an explicit "which layer does this belong to?" question on every change.

---

## ADR-005 â€” Status changes only through an explicit transition operation

**Context.** Requirements forbid clients changing status by writing an arbitrary field.

**Decision.** `Ticket.status` is read-only in every serializer. The only writer is
`workflows.services.transition_ticket()`, which validates the transition table, the actor's
permission, and per-transition preconditions inside a transaction, then appends
`TicketStatusHistory`.

**Consequences.** No illegal state is reachable through the API, and every change is auditable
with an actor and timestamp. Cost: bulk status edits require looping over the transition service.

---

## ADR-006 â€” UUIDv7 primary keys plus human-readable ticket keys

**Context.** Internal identifiers must not leak volume/ordering to clients and must be safe to
expose in URLs; humans need a short reference such as `ENG-1042`.

**Decision.** `UUIDField(primary_key=True, default=uuid.uuid7)` for major entities (Python 3.14
ships `uuid.uuid7`, giving time-ordered UUIDs with good B-tree insert locality, unlike v4).
The human key is stored separately as `Ticket.key`, unique, composed of `Project.key` + a
per-project sequential number.

**Consequences.** URLs are opaque and non-enumerable; new rows append at the index end instead
of scattering. Cost: 16-byte keys and slightly larger indexes than `bigint`.

---

## ADR-007 â€” Concurrency-safe ticket key generation

**Context.** Two requests can create tickets in the same project simultaneously; both must
receive distinct keys, and `ENG-1042` must never be handed out twice.

**Options.**
* `max(number) + 1` on read: race-prone, rejected.
* PostgreSQL `SEQUENCE` per project: correct on Postgres, but DDL per project and
  Postgres-specific, breaking the documented SQLite fallback (ADR-008).
* Counter row per project with `SELECT ... FOR UPDATE` plus a unique constraint and a bounded
  retry on `IntegrityError`.

**Decision.** The third option, in `tickets/services/keys.py`:
1. `transaction.atomic()`; `TicketKeySequence.objects.select_for_update().get_or_create(project=...)`
   serialises concurrent creators on PostgreSQL.
2. Increment and flush the counter.
3. Insert the ticket; the **unique constraint on `Ticket.key` is the real guarantee**. If it
   fires, each attempt runs in its own atomic block (savepoint), so the poisoned transaction is
   rolled back and the operation is retried up to `TICKET_KEY_MAX_RETRIES` times.

**Consequences.** Correct on PostgreSQL (lock) *and* on SQLite (constraint + retry), so the
rule is testable without Docker. Cost: a retry path that must stay small and a gap-tolerant
counter (a rolled-back attempt may burn a number â€” acceptable, documented).

---

## ADR-008 â€” PostgreSQL in production, SQLite permitted only as an explicit local fallback

**Context.** The target database is PostgreSQL. The current host has no PostgreSQL server and no
running Docker daemon, so a contributor may be unable to start one.

**Decision.** `config/settings/base.py` selects the engine from `DB_ENGINE` (`postgres` default,
`sqlite` opt-in for local development and for the default test run). The Docker environment and
the deployment guide use PostgreSQL.

**Consequences.** The whole domain test suite is runnable anywhere, which keeps the feedback loop
fast. The trade-off is explicit: `SELECT ... FOR UPDATE` has no effect on SQLite, so
Postgres-only behaviour (row locking, `inet` columns, partial indexes) is covered by tests marked
`@pytest.mark.postgres` and skipped when the engine is SQLite. **No claim of PostgreSQL
verification is made unless those tests actually ran against PostgreSQL.**

That gap is closed by CI (`.github/workflows/ci.yml`): the same suite runs with `DB_ENGINE=postgres`
against a PostgreSQL 17 service, and the job **fails if any test is skipped**, so the `postgres`
tests cannot quietly disappear. This is not theoretical — the first PostgreSQL run failed 38 tests
with `FOR UPDATE cannot be applied to the nullable side of an outer join` in `transition_ticket()`, a
bug that would have made every status transition return HTTP 500 in production while the SQLite suite
stayed green. `config/settings/test.py` therefore selects the engine from `DB_ENGINE` instead of
hard-coding SQLite.

---

## ADR-009 â€” Celery + Redis for notifications, with idempotency in the data model

**Context.** Notification fan-out can be slow and must not fail the user's request. Retried
tasks must not spam duplicates.

**Decision.** The write path only inserts a `Notification` row and calls
`send_notification_task.delay(notification_id)`. The task is idempotent through the data, not
through hope: `Notification.dedup_key` is unique per (recipient, event, subject), the task
re-checks `is_sent` before dispatch, and re-delivery is a no-op. Tests run with
`CELERY_TASK_ALWAYS_EAGER = True`, so the notification logic is exercised without a broker.

**Consequences.** Reliable under at-least-once delivery, and the async path is testable. Cost:
a `dedup_key` must be derived for every event type.

---

## ADR-010 â€” Attachments are private objects served through an authorising endpoint

**Context.** Attachments can contain customer data, logs or credentials.

**Decision.** Files are stored via `django-storages` (MinIO/S3 in Docker, filesystem in local
dev) under a random UUID object name that never contains the original filename. The bucket is
private; no public URL is ever returned by the API. Download goes through
`GET /api/v1/attachments/<uuid>/download/`, which re-checks project membership and permission
and then streams the object. Upload enforces an extension+content-type allow-list and a size
limit (`ATTACHMENT_MAX_BYTES`), and stores a SHA-256 checksum.

**Consequences.** Object-level authorisation is enforced on every read, matching the
"no insecure direct object reference" requirement. Cost: downloads consume application
bandwidth instead of coming straight from object storage.

---

## ADR-011 â€” One audit mechanism, plus the workflow's own business record

**Context.** The requirements ask for an audit trail *and* for status history, and warn against
duplicating the same event across mechanisms.

**Decision.** Two records with non-overlapping purposes:
* `TicketStatusHistory` â€” a **business record**: "this ticket went NEW â†’ TRIAGED by X, with this
  comment". It is part of the workflow domain and is shown in the ticket timeline.
* `AuditEvent` â€” a **compliance record**: who did what, to which object, from which IP, when,
  covering all modules (project changes, membership changes, assignments, permission changes),
  with a single `action` vocabulary.

A transition therefore writes both, and the duplication is deliberate and bounded: the audit row
references the history row's id in its metadata instead of copying the payload. `AuditEvent` is
append-only and exposed read-only; production hardening revokes `UPDATE`/`DELETE` on the table
from the application role (deployment guide).

**Consequences.** No event is recorded in two generic audit tables; the workflow's business
timeline stays queryable on its own. Cost: two writes per transition in the same transaction.

---

## ADR-012 â€” Effective permission = system role Ã— project membership

**Context.** "A user's access must depend on both their system role and their membership in a
particular project."

**Decision.** `User.system_role` (`ADMIN`, `PROJECT_MANAGER`, `ENGINEER`, `REPORTER`) is global.
`ProjectMembership.role` is per project. All object-level checks live in
`apps/projects/permissions.py` as pure functions (`can_view_project`, `can_edit_ticket`,
`can_transition_ticket`, `can_assign`, `can_manage_members`, ...). DRF permission classes
(`apps/*/permissions.py`) are thin adapters that call those functions, and the same functions are
re-checked inside services.

**Consequences.** One authoritative rule set, reused by API and services, and unit-testable
without HTTP. Cost: services must receive the actor explicitly (no hidden `request.user`).

---

## ADR-013 â€” REST with path-based versioning and generated OpenAPI

**Decision.** All endpoints under `/api/v1/`. `drf-spectacular` generates the OpenAPI 3 schema at
`/api/schema/`, Swagger UI at `/api/docs/`, ReDoc at `/api/redoc/`. Errors use a single
normalised envelope produced by a custom exception handler in `common/exceptions.py`.

**Consequences.** Enables backwards-compatible evolution and generated client types later.
Cost: versioned URL routing must be maintained.

---

## ADR-014 â€” Frontend: React + TypeScript + Vite, feature-sliced, server state in a query cache

**Decision.** React with TypeScript, Vite for build/dev. Server state via TanStack Query
(caching, refetch, optimistic-free simplicity); client/UI state local; form state via
react-hook-form + zod schemas that mirror backend validation. Folder layout by feature
(`src/features/tickets/...`, `src/features/projects/...`) with a shared `src/components` design
system. Routes are guarded by an auth boundary component; the backend remains the source of
truth for permissions (the UI only hides what the API would refuse anyway).

**Consequences.** Clear separation of server cache vs UI state, reusable components. Cost: a
query-cache mental model to learn; documented in the learning guide.

---

## ADR-015 â€” Interface language and localisation

**Context.** The product is described in English, the stakeholders speak Persian as well.

**Decision (assumption, reversible).** v1 ships an **English** UI with `en` as the only locale
(`LANGUAGE_CODE = "en-us"`, `USE_TZ = True`, all timestamps stored in UTC and formatted in the
browser's time zone). No RTL layout work in v1. Adding `fa` later means: add Django locales for
backend messages, add `i18n` to the frontend, and set `dir="rtl"` on the document for that
locale. See `docs/requirements/assumptions-and-open-questions.md`.

---

## ADR-016 — Define every domain model before the first migration; implement behaviour phase by phase

**Context.** The delivery plan is phase-ordered (accounts ? projects ? tickets ? workflow ?
collaboration). But the models are not independent: `AuditEvent` and `Notification` reference
`Project` and `Ticket`; `TicketStatusHistory` references `Ticket`; `Ticket` references `Project`.
A migration cannot be generated for an app whose foreign keys point at a model that does not exist
yet, so a strictly phase-ordered *model* rollout would require placeholder models, dangling
dependencies, or an artificial `AuditEvent` without project/ticket context.

**Options.** (a) Strictly phase-ordered models with temporary migrations that add FKs later;
(b) all models in one pass, behaviour phase by phase; (c) drop the cross-module foreign keys and
store loose UUIDs.

**Decision.** (b). All models and constraints were authored together and migrated once, in
dependency order (`accounts ? projects ? tickets ? workflows ? comments ? attachments ? notifications
? audit`). Behaviour — permissions, services, API, tests — still arrived in the documented phases.
Option (c) was rejected: losing referential integrity for the audit and notification tables would
trade a real guarantee for cosmetic sequencing.

**Consequences.** The first commit contains more schema than any single feature needs, so the
migration diff must be reviewed as a whole (indexes, `on_delete`, constraints). In exchange, there
are no throwaway migrations, no half-referenced tables, and each later phase only adds behaviour.
The phase reports therefore describe *logic* milestones, while `docs/architecture/erd.md` remains the
authoritative schema view.
