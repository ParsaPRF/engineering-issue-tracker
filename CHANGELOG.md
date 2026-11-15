# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-11-15

First complete delivery of the Engineering Issue & Ticket Tracking System: a modular-monolith
backend, a React/TypeScript SPA, container infrastructure, and the documentation set that explains
the decisions behind them.

### Added

**Backend (Django 5.2 LTS, Python 3.14, DRF)**

- Nine bounded contexts: `accounts`, `projects`, `tickets`, `workflows`, `comments`, `attachments`,
  `notifications`, `audit`, `reports`, each with its own models, services, selectors, API and tests.
- Custom email-based user model with four system roles and a project-level role per membership; the
  effective permission is the combination of both (ADR-012).
- Session authentication with CSRF protection for the SPA — no JWT, nothing stored in
  JavaScript-readable storage (ADR-003).
- Ticket aggregate with UUIDv7 primary keys, human-readable per-project keys (`ENG-1042`), labels,
  components, and concurrency-safe key allocation (row lock + unique index + savepoint retry,
  ADR-007).
- Explicit workflow state machine with 10 statuses, 19 declared transitions, role rules, comment and
  assignee guards, and an append-only status timeline (ADR-005).
- Assignment rules (managers assign anyone, engineers claim unassigned tickets, reporters are not
  assignable), with eligibility enforced in the service layer.
- Comments with an edit window and soft delete; private attachments validated by extension, size and
  content type and served only through an authorising download endpoint (ADR-010).
- In-app notifications created transactionally and dispatched through Celery, made idempotent by a
  unique dedup key (ADR-009).
- Append-only audit trail with sanitised metadata, immutable in Python and hardened at the database
  level in the deployment guide (ADR-011).
- Dashboard, workload and recent-activity reports, all permission-scoped in SQL.
- OpenAPI 3 schema (51 paths) with zero warnings, Swagger/ReDoc, and an error envelope shared by
  every endpoint.

**Frontend (React 19, TypeScript, Vite)**

- Thirteen screens: login/register, dashboard, projects, project detail (members, components,
  tickets), ticket list/create/detail, my assignments, team, notifications, reports, profile, plus
  an admin audit view and a 404 page.
- A single HTTP layer that owns credentials, the CSRF header, the error envelope and authenticated
  file downloads; no screen calls `fetch` directly.
- Transition buttons rendered from the API's transition catalogue, so the UI cannot offer a move the
  backend would reject.
- Design tokens with separate status/priority/severity ramps (priority `CRITICAL` and severity
  `CRITICAL` stay visually distinct), responsive from 360 px to 1920 px.

**Infrastructure**

- Dockerfiles for the API (gunicorn, non-root, health check, wait-for-database entrypoint) and for
  the SPA (multi-stage build served by Nginx).
- Docker Compose stack: PostgreSQL 17, Redis 7, MinIO with a private bucket created on first boot,
  the API, a Celery worker, Celery beat, and Nginx as the single origin.
- GitHub Actions CI: lint/schema/migrations, the full test suite against PostgreSQL 17 with no skips
  allowed, the frontend build, and both container images built plus a container health smoke test.

**Documentation**

- `docs/architecture/`: system overview, 16 ADRs, module responsibilities, ERD, workflow
  specification.
- `docs/requirements/`: functional and non-functional requirements, 17 use cases, and the
  assumptions/open questions list.
- `docs/api/`: endpoint reference and the generated OpenAPI schema.
- `docs/development/`: development, testing and deployment guides.
- `docs/learning/`: a phase-by-phase developer learning guide.

### Verification

- 228 tests pass locally on SQLite (1 PostgreSQL-only test skipped by design).
- 229 tests pass against PostgreSQL 17 in CI, **0 skipped**, including the threaded concurrent
  ticket-key test.
- OpenAPI schema generates with zero errors and zero warnings; `ruff` is clean; no pending
  migrations.
- The SPA was exercised against the real backend through the Vite proxy: CSRF, session login,
  authenticated data, transition catalogue, anonymous 403.

### Fixed

- **`FOR UPDATE` across a nullable join.** `transition_ticket()` locked the ticket with
  `select_related("assignee")`, and because `assignee` is nullable PostgreSQL rejected the lock
  (`FOR UPDATE cannot be applied to the nullable side of an outer join`). SQLite ignores the clause,
  so every status transition would have returned HTTP 500 in production while the local suite stayed
  green. Found by the first PostgreSQL CI run; the lock now joins only non-nullable relations.
- **Soft-deleted attachments stayed downloadable.** The `is_deleted` filter existed only on the list
  endpoint, so a deleted file remained reachable through its download URL.
- **Priority ordering was alphabetical.** `?ordering=priority` sorted `CRITICAL` before `LOW`; the
  API now orders by a numeric rank annotation.
- **`member_count` reported 1.** Filtering on a multi-valued relation and counting it in the same
  query reused the join; visibility now uses an `EXISTS` subquery.
- **CI could have reported a failing suite as green.** Piping `pytest` into `tee` without
  `pipefail`; fixed before the pipeline was trustworthy.
- **A documentation file became invalid UTF-8** when a shell tool wrote an em dash in the Windows
  code page. Repaired, and `backend/tools/check_encoding.py` now reports such files.

### Known limitations

- `docker compose up` was not executed end-to-end during delivery (no Docker daemon on the build
  workstation). CI builds both images and boots the API container against PostgreSQL; the full stack,
  MinIO bucket creation in a live run, and Celery against a live Redis remain to be exercised.
- Notifications are in-app only; the delivery seam exists but no email/SMS transport is configured.
- Browser rendering was not visually verified; the bundle and its network path were.

[1.0.0]: https://github.com/ParsaPRF/engineering-issue-tracker/releases/tag/v1.0.0