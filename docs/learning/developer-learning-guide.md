# Developer Learning Guide

This is the mentor-mode companion to the codebase: for each delivery phase it answers *what was
built*, *why it was built that way*, *which files to read*, *how the pieces talk to each other*,
*which principles are in play*, *what to study next*, *how to verify it yourself*, and *which
mistakes to avoid*. Read it next to the code, not instead of it.

Ordered reading path (about two hours for the whole system):

```
common/models.py → common/exceptions.py → apps/projects/permissions.py
→ apps/projects/services/projects.py → apps/tickets/services/keys.py
→ apps/workflows/state_machine.py → apps/workflows/services.py
→ apps/tickets/api/views.py → apps/comments/services.py → apps/attachments/services.py
→ apps/notifications/services.py → apps/reports/selectors.py
→ common/views.py (health) → docker-compose.yml
```

---

## Phase 1 — Requirements and architecture

**What was built.** `docs/architecture/*` (system overview, 16 ADRs, module responsibilities, ERD,
workflow) and `docs/requirements/*` (functional, non-functional, use cases, assumptions).

**Why this way.** Two documents carry most of the value: the **ERD** (which forces you to decide
`on_delete` behaviour and uniqueness constraints before any code exists) and the **ADR log** (which
records the *options you rejected*). Code tells you what the system does; only an ADR tells you why
the obvious alternative was not chosen — and that is what a maintainer needs six months later.

**Important files.** `docs/architecture/architecture-decisions.md` (esp. ADR-003 auth, ADR-005
status writes, ADR-007 key allocation, ADR-012 permissions), `docs/architecture/erd.md`.

**How modules relate.** The dependency rule is one-way: `api → services → selectors → models`, with
`projects.permissions` as a shared kernel everyone may call. `workflows` receives the ticket's rules
as arguments so `projects` never has to import it. `reports` depends on everyone and nobody imports it
at module level.

**Principles in play.** Separation of concerns; explicit business rules; single source of truth;
documented trade-offs; YAGNI (no microservices, no event bus, no generic repository).

**Study.** "Architecture Decision Records" (Nygard); Django's docs on *Design philosophies*; the
difference between *bounded context* and *Django app*.

**Verify.** Open `docs/architecture/erd.md` beside `apps/*/models*.py` and check every `on_delete` and
every `UniqueConstraint` exists in the code.

**Avoid.** Writing architecture documents *after* the code and calling them design. The tell is a
document that only describes what exists and never mentions an alternative.

---

## Phase 2 — Backend foundation

**What was built.** Django 5.2 project with split settings, `common/` primitives, the custom user
model, nine app skeletons, pinned requirements, pytest/ruff configuration.

**Why this way.**
* **Custom user model before the first migration.** Retrofitting one means rewriting every FK in the
  project. `accounts.User` is created in the first migration on purpose.
* **Split settings** (`base` / `development` / `production` / `test`): production *refuses to boot*
  with the development secret, so a misconfiguration is a startup failure instead of a silent
  vulnerability.
* **`common/` is not a Django app** because it owns no tables; it holds abstract bases, the error
  envelope and pagination.

**Important files.** `backend/config/settings/base.py`, `config/settings/test.py`,
`common/models.py` (UUIDv7 + timestamps), `common/exceptions.py` (the error envelope),
`apps/accounts/managers.py`, `backend/pyproject.toml`.

**How they relate.** Every model inherits `UUIDModel` / `TimeStampedModel`; every API error funnels
through `envelope_exception_handler`; every list endpoint uses `DefaultPagination`.

**Principles.** DRY (bases, one error shape), fail-fast configuration, 12-factor config, minimal
dependencies (no whitenoise, no SimpleJWT, no DRF extras nobody uses).

**Study.** Django settings composition; `django-environ`; UUIDv7 vs UUIDv4 (index locality);
`REST_FRAMEWORK["EXCEPTION_HANDLER"]`.

**Verify.**
```bash
cd backend && .venv/Scripts/python manage.py check
.venv/Scripts/python manage.py sqlmigrate accounts 0001 | head -40
.venv/Scripts/python -c "import uuid; print(uuid.uuid7())"
```

**Avoid.** Committing `.env`; using `SECRET_KEY` defaults in production; putting business logic in
`settings`; adding an app to `INSTALLED_APPS` that has no models and no purpose.

---

## Phase 3 — Authentication and permissions

**What was built.** Registration, session login/logout, CSRF-protected unsafe endpoints, profile
management, password change with session invalidation, Admin-only role/activation endpoints, and the
audit vocabulary.

**Why this way.**
* **Session cookies instead of JWT** (ADR-003): the browser client does not need tokens, the session
  can be revoked server-side by deleting a row, and the token never lives in JavaScript-accessible
  storage.
* **`HttpOnly` session cookie, readable CSRF cookie** — the two cookies have different jobs.
* **The inactive-account disclosure rule**: "your account is inactive" is only revealed *after* the
  password checks out, so the login form cannot be used to enumerate accounts.
* **Deactivation instead of deletion** keeps every ticket, comment and audit row attributable.

**Important files.** `apps/accounts/services/auth.py` (login/logout + the disclosure rule),
`apps/accounts/api/views.py` (CSRF-protected `LoginView`/`RegisterView`),
`apps/accounts/services/users.py` (`invalidate_user_sessions`, last-admin protection),
`common/permissions.py`, `apps/accounts/roles.py`.

**How they relate.** A view validates shape → a service checks credentials/permissions and writes the
audit event → the serializer renders the user. `apps/audit/services.record` is called from the write
path, never from a signal.

**Principles.** Least privilege (registration grants REPORTER), fail-closed defaults
(`IsAuthenticated` globally), defence in depth (CSRF + same-origin + cookie flags), explicitness (no
hidden signal-based side effects).

**Study.** OWASP: *Session Management* and *CSRF* cheat sheets; Django's `authenticate`/`login` and
session key rotation; why DRF's `SessionAuthentication` returns 403 for anonymous requests.

**Verify.** `pytest apps/accounts -v` — especially `test_login_requires_a_csrf_token_when_csrf_is_enforced`
and `test_inactive_account_is_reported_only_when_the_password_is_correct`.

**Avoid.** `@csrf_exempt` on login; tokens in `localStorage`; returning different errors for unknown
email vs wrong password; forgetting that `APIView` is CSRF-exempt by default.

---

## Phase 4 — Projects and the permission kernel

**What was built.** Project CRUD + archive/restore, memberships with project roles, components,
project statistics, and the permission kernel that every other module uses.

**Why this way.**
* **Effective permission = system role × project membership.** Four system roles alone cannot answer
  "may this person edit *this* ticket?".
* **Pure functions in `projects/permissions.py`**, not DRF permission classes, because the same rule
  must be enforced in three places: the API, the service, and the tests.
* **Archive, don't delete.** `Ticket.project` uses `PROTECT`, so a mistaken `delete()` raises.
* **`Exists(OuterRef)` for visibility** to avoid the join/annotate collision described in §7 of the
  development guide.

**Important files.** `apps/projects/permissions.py` (read this first — it is the whole authorisation
model in one file), `apps/projects/services/memberships.py` (last-manager invariant),
`apps/projects/selectors/projects.py` (permission-scoped queries), `apps/projects/api/views.py`.

**How they relate.** Views call the service; the service calls `can_manage_project`; selectors scope
querysets so foreign objects are simply absent (the API then answers 404).

**Principles.** Single source of truth for rules; fail closed; invariants enforced in the service and
mirrored in `Model.clean()`; 404-not-403 for foreign objects.

**Study.** Django model `constraints` (`UniqueConstraint`, `CheckConstraint`); `on_delete` semantics
(`PROTECT` vs `CASCADE` vs `SET_NULL`); object-level permissions in DRF; `Exists`/`OuterRef`.

**Verify.** `pytest apps/projects -v`; then break `can_manage_project` (return `True`) and watch the
authorisation tests fail — a good way to confirm a test actually tests something.

**Avoid.** Putting permission checks only in the view (the admin and Celery bypass views); using
`distinct()` to "fix" double counting when the real bug is a join; letting a project end up with no
manager.

---

## Phase 5 — Tickets and the workflow engine

**What was built.** Ticket creation with atomic key allocation, filtering/search/ordering, assignment,
the state machine with guards, the transition operation, the timeline, and a transition catalogue
endpoint that drives the UI.

**Why this way.**
* **Key allocation (ADR-007)** is the most instructive part: `MAX+1` races; a per-project counter row
  with `select_for_update` serialises on PostgreSQL; the unique constraint on `Ticket.key` is the real
  guarantee; the retry runs in its own savepoint so a lost race does not poison the transaction.
* **The workflow is a table**, not `if` statements: `TRANSITION_TABLE` is data that the service, the
  API and the tests all read. That is why the matrix test can be exhaustive.
* **`status` is unwritable through the API** (ADR-005). Sending it is an explicit error, not a silent
  ignore, so a client cannot believe it succeeded.
* **Semantic ordering**: `ordering=priority` uses a CASE rank, because alphabetical order puts
  `CRITICAL` before `LOW`.

**Important files.** `apps/workflows/state_machine.py`, `apps/workflows/services.py` (the lock +
validate + apply + history + audit + notify sequence), `apps/tickets/services/keys.py`,
`apps/tickets/services/tickets.py`, `apps/tickets/api/filters.py`,
`apps/workflows/tests/test_workflow_matrix.py`.

**How they relate.** `tickets.services` creates tickets and calls `workflows.services.record_initial_status`;
`workflows.services.transition_ticket` is the only writer of `Ticket.status` and calls
`projects.permissions.can_transition_ticket` with the rule's allowed roles.

**Principles.** Concurrency safety by construction; single writer for a critical field; explicit state
machine; transaction boundaries as a first-class concern; retry with a bounded budget.

**Study.** Django transactions (`atomic`, savepoints, `select_for_update`), isolation levels, why
`MAX()+1` is wrong, state machine design, idempotency keys.

**Verify.**
```bash
pytest apps/workflows -v          # includes the exhaustive matrix
pytest apps/tickets/tests/test_ticket_keys.py -v
```
Then, on PostgreSQL: `pytest -m postgres -v` (the threaded key test).

**Avoid.** Changing status with `ticket.save()` anywhere; validating the transition *before* taking
the row lock; writing history outside the transaction; retrying without a savepoint.

---

## Phase 6 — Collaboration, notifications and audit

**What was built.** Comments with edit-window and soft delete, private attachments with an authorising
download, in-app notifications with a Celery seam, and the append-only audit trail.

**Why this way.**
* **Soft delete for comments** keeps the audit trail's anchors valid; **hard delete of the stored
  object** for attachments because keeping "deleted" bytes is a privacy problem — the row stays for the
  record, the bytes go.
* **Attachments are never public.** No storage URL in any response; download passes through a view
  that re-checks the project. That is what defeats IDOR on files.
* **Notifications: create the row in the transaction, deliver asynchronously, dedupe in the model.**
  The unique `dedup_key` is what makes at-least-once delivery safe.
* **One audit mechanism** (`AuditEvent`) plus the workflow's own business timeline (`TicketStatusHistory`)
  with distinct purposes (ADR-011).

**Important files.** `apps/comments/services.py`, `apps/attachments/validators.py`,
`apps/attachments/services.py` (note `transaction.on_commit` for storage deletion),
`apps/notifications/services.py` (audience + dedup), `apps/notifications/tasks.py`,
`apps/audit/services.py` (sanitisation).

**How they relate.** Services call `notify_*` helpers and `audit_record`; notification helpers never
call other services back (no cycles); the Celery task only touches `Notification`.

**Principles.** Least privilege on files; defence in depth (extension allow-list + content type +
`Content-Disposition: attachment`); idempotency by data, not hope; retention as an explicit decision.

**Study.** Stored-XSS vectors (SVG/HTML), `Content-Disposition`, `FileResponse`, Celery retry
semantics (`acks_late`, `reject_on_worker_lost`), `transaction.on_commit`.

**Verify.** `pytest apps/comments apps/attachments apps/notifications apps/audit -v`.

**Avoid.** Serving uploads from `/media`; trusting the client's `Content-Type`; deleting storage inside
the transaction (rollback leaves a row pointing nowhere); notifying the actor about their own action.

---

## Phase 7 — Frontend

**What was built.** React + TypeScript + Vite SPA: login, dashboard, projects, project detail, ticket
list/create/detail, my assignments, team, notifications, reports, profile. Server state in TanStack
Query, forms in react-hook-form + zod, routing in react-router with a protected-route wrapper.

**Why this way.**
* **Server state is not application state.** Tickets, projects and notifications live in a query cache
  with explicit invalidation; the UI does not copy them into `useState`.
* **The UI never hard-codes the workflow.** Status buttons come from
  `GET /workflows/transitions/?ticket=…`, so a backend rule change cannot produce a button that 400s.
* **The frontend is not a security boundary.** `RoleGate` hides what a user cannot do, but every rule
  is re-checked by the API (and by the service underneath it).

**Important files.** `src/lib/http.ts` (fetch + CSRF + error envelope), `src/auth/AuthProvider.tsx`,
`src/app/router.tsx`, `src/features/tickets/…`, `src/features/tickets/TicketDetail`'s transition panel.

**How they relate.** `http.ts` is the only place that knows about cookies and CSRF; features call typed
`api.ts` functions; components stay presentational.

**Principles.** Separation of server/UI state; single API client; explicit loading/empty/error states;
accessible controls; no token in storage.

**Study.** TanStack Query's cache lifecycle (`staleTime`, `invalidateQueries`); React Hook Form +
zod resolver; same-origin cookies vs CORS; why `credentials: 'include'` is required.

**Avoid.** Storing a token in `localStorage`; duplicating backend validation rules *instead of* showing
server errors; `useEffect`-driven data fetching when the query cache exists; rendering a status button
the API would reject.

---

## Phase 8 — Testing and quality

**What was built.** 228 tests (1 skipped: PostgreSQL-only) covering models, services, workflow matrix,
authorisation, uploads, notifications, audit and reporting.

**Why this way.**
* **Test the rule where it lives.** Service tests for business rules; API tests for HTTP contracts;
  permission tests for the role matrix.
* **Expectations derived from data.** The workflow matrix iterates `TRANSITION_TABLE` itself, so it
  cannot drift; if the table changes, the test changes.
* **Honest skips.** PostgreSQL-only tests are marked, not weakened: a test that silently stops testing
  row locking is worse than none.

**Important files.** `backend/conftest.py` (fixtures + the `postgres` skip hook),
`apps/workflows/tests/test_workflow_matrix.py`, `apps/attachments/tests/test_attachments.py` (the
rejections matter more than the happy path), `backend/tests/test_project_structure.py`.

**Principles.** Fast feedback; arrange-act-assert; one behaviour per test; test doubles only at
external boundaries (here: none — Celery runs eagerly instead).

**Study.** pytest fixtures and markers, pytest-django's `db`/`transaction` markers, factory_boy
`post_generation`, the difference between a unit and an integration test in a monolith.

**Verify.** `pytest -q`, then deliberately break a rule and confirm a test fails. Also read the skip
summary: it tells you what is *not* verified.

**Avoid.** Asserting on implementation details; tests that pass for the wrong reason (e.g. a factory
that makes a user whose password does not authenticate); hiding a Postgres-only failure behind a skip
that is never run.

---

## Phase 9 — Deployment

**What was built.** Dockerfiles for backend and frontend, an entrypoint that waits for the database and
collects static files, Nginx config for a single-origin deployment, and a compose stack with health
checks and named volumes.

**Why this way.**
* **Migrations are a release step, not a boot step** (`ENABLE_MIGRATIONS=0` by default): schema changes
  deserve review and a backup.
* **Static files in a shared volume** so Nginx serves them without touching Django.
* **Health checks test the application**, not just the port (`/health/` pings the database).
* **Startup guards** (`:?` in compose) refuse to start with placeholder secrets.

**Important files.** `docker/backend.Dockerfile`, `docker/frontend.Dockerfile`,
`docker/entrypoint.sh`, `docker/nginx.conf`, `docker-compose.yml`,
`config/settings/production.py`.

**Principles.** 12-factor configuration; least-privilege containers (non-root user); immutable images;
explicit release steps; observable health.

**Study.** Gunicorn worker models (sync vs gthread), Nginx `proxy_pass` semantics (a trailing slash
changes the URI), `pg_dump`/restore discipline, `python manage.py check --deploy`.

**Verify.** `docker compose --env-file .env.example config` (parses without a daemon), then the real
`docker compose up --build -d` on a machine with Docker, followed by the deployment guide's checklist.

**Avoid.** `DEBUG=True` in production; baking secrets into images; running migrations automatically at
container start; serving attachments from `/media`; forgetting to back up object storage alongside the
database.

---

## Concept glossary (the ones that actually matter here)

| Term | One-line explanation | Where to see it |
| --- | --- | --- |
| Service layer | Functions that own a business operation and its transaction | `apps/*/services/` |
| Selector | Reusable, permission-scoped read query | `apps/*/selectors/` |
| Domain error | Exception carrying a stable `code` and HTTP status, raised by services | `common/exceptions.py` |
| Error envelope | One JSON shape for every failure | `common/exceptions.py` |
| Transaction overload | Two requests reading the same row and both writing a derived value | ADR-007 |
| `select_for_update` | Row lock held until commit (PostgreSQL only) | `apps/tickets/services/keys.py` |
| Savepoint | Nested transaction marker that makes a failed attempt retryable | `create_with_allocated_key` |
| IDOR | Reaching another user's object by guessing its id | `get_visible_*` selectors |
| CSRF | Forcing a logged-in browser to make an unwanted state-changing request | `LoginView`, `http.ts` |
| N+1 query | One query per row because a relation was not joined | `selectors/*` |
| Dedup key | Unique key that makes retried delivery idempotent | `notifications/services.py` |
| Append-only | Rows are inserted and read, never updated or deleted | `audit/models.py` |
| Soft delete | Row retained, hidden from reads | `Comment.is_deleted`, `Attachment.is_deleted` |
| Server state | Data owned by the API, cached on the client | TanStack Query |
| Fail closed | Unknown/ambiguous → deny | `projects/permissions.py` |

## Suggested exercises (in increasing difficulty)

1. Add a `WONT_FIX` status: update the state machine, the matrix test will tell you exactly what else
   needs updating.
2. Add a "due date reminder" notification: a Celery beat task + a new event type + tests.
3. Add ticket watchers (`TicketWatcher`): extend `ticket_audience`, nothing else should need to change —
   if more than that changes, the module boundary is leaking.
4. Implement email delivery behind `notifications/tasks.send_notification` without touching any service.
5. Replace the SQLite fallback with a docker-based Postgres in CI and run `pytest -m postgres`.