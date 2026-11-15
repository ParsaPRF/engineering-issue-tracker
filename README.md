# Engineering Issue & Ticket Tracking System

A production-oriented ticket tracking system for engineering teams: multiple projects, a
controlled ticket lifecycle, assignment, collaboration, notifications, an immutable audit trail
and a reporting dashboard.

Built as a **modular monolith**: one Django deployment whose business capabilities are separate
apps with their own models, services, API and tests.

| Layer | Stack |
| --- | --- |
| Backend | Python 3.14, Django 5.2 LTS, Django REST Framework, PostgreSQL, Redis, Celery |
| Frontend | React, TypeScript, Vite |
| Infrastructure | Docker, Docker Compose, Nginx, MinIO (S3-compatible) |
| Quality | pytest + pytest-django, OpenAPI 3 via drf-spectacular, ruff |

## Documentation map

| Document | Contents |
| --- | --- |
| [System overview](docs/architecture/system-overview.md) | product, actors, topology, layering rules |
| [Architecture decisions](docs/architecture/architecture-decisions.md) | 15 ADRs: context, options, decision, consequences |
| [Module responsibilities](docs/architecture/module-responsibilities.md) | what each app owns and provides |
| [ERD](docs/architecture/erd.md) | entities, fields, constraints, indexes, deletion behaviour |
| [Workflow](docs/architecture/workflow.md) | states, transition table, guards, side effects |
| [Functional requirements](docs/requirements/functional-requirements.md) | FR-1 … FR-10 with verification pointers |
| [Non-functional requirements](docs/requirements/non-functional-requirements.md) | security, performance, reliability, operability |
| [Use cases](docs/requirements/use-cases.md) | UC-01 … UC-17 |
| [Assumptions and open questions](docs/requirements/assumptions-and-open-questions.md) | reversible assumptions, questions, environment constraints |
| [API overview](docs/api/api-overview.md) | endpoint reference and error envelope |
| [Development guide](docs/development/development-guide.md) | how to run, test, and extend |
| [Testing guide](docs/development/testing-guide.md) | test layout, markers, writing new tests |
| [Deployment guide](docs/development/deployment-guide.md) | Docker Compose, Nginx, TLS, backups, hardening |
| [Developer learning guide](docs/learning/developer-learning-guide.md) | mentor-mode explanations per phase |

## Quick start (local, no Docker)

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate on Unix
pip install -r requirements/development.txt
cp ../.env.example .env         # then edit; DB_ENGINE=sqlite works for local dev
python manage.py migrate
python manage.py seed_demo      # optional: demo users, projects and tickets
python manage.py runserver

# frontend (second terminal)
cd frontend
pnpm install
pnpm dev
```

API docs: <http://127.0.0.1:8000/api/docs/> · Frontend: <http://127.0.0.1:5173>

## Quick start (Docker Compose)

```bash
cp .env.example .env            # set real secrets; compose refuses to start with placeholders
docker compose up --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

| Service | URL |
| --- | --- |
| App (via Nginx) | <http://localhost:8080> |
| API docs | <http://localhost:8080/api/docs/> |
| MinIO console | <http://localhost:9001> |

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest          # full suite
cd backend && .venv/Scripts/python -m pytest -m postgres   # PostgreSQL-only checks
```

## Repository layout

```
eng-tracker/
  backend/
    config/            # settings package (base/development/production/test), urls, celery, wsgi/asgi
    apps/
      accounts/        # users, profiles, auth, system roles
      projects/        # projects, memberships, components, permission kernel
      tickets/         # tickets, labels, key allocation, assignment
      workflows/       # state machine, transitions, status history
      comments/        # ticket discussion
      attachments/     # private file storage + authorising download
      notifications/   # in-app notifications + Celery tasks
      audit/           # append-only audit trail
      reports/         # dashboard aggregation (no models)
    common/            # abstract models, permissions, pagination, exception envelope
    requirements/      # base/development/production/test pins
    manage.py
  frontend/            # React + TypeScript + Vite SPA
  docker/              # Dockerfiles, Nginx config, entrypoints
  docs/                # architecture, requirements, api, development, learning
  docker-compose.yml
  .env.example
```

## Status

Implementation follows the nine phases in the project brief. **Nothing is marked complete merely
because files exist** — every row below is a command that was actually executed, with its real result.

| Check | Command | Result |
| --- | --- | --- |
| Backend test suite | `pytest apps tests -q` | **228 passed, 1 skipped** in ~6 s |
| Skipped test | `pytest -m postgres` | The threaded ticket-key race test — needs PostgreSQL (ADR-008) |
| Lint | `ruff check apps common config tests` | `All checks passed!` |
| Django checks | `manage.py check` | `System check identified no issues (0 silenced).` |
| Migrations | `manage.py makemigrations --check --dry-run` | `No changes detected` |
| OpenAPI schema | `manage.py spectacular` | `Errors: 0`, `Warnings: 0`, 51 paths written to `docs/api/openapi.yaml` |
| Demo data | `manage.py seed_demo` (twice) | 5 users, 1 project, 4 components, 6 tickets; second run created nothing (idempotent) |
| HTTP smoke test | real `runserver` + cookie/CSRF session | health ok, login ok, ticket list, transitions, dashboard, audit 403 for non-admin, bad CSRF 403 |
| Compose file | `docker compose --env-file .env.example config` | exit 0 (parsed without a Docker daemon) |
| Frontend typecheck + build | `pnpm build` in `frontend/` | `tsc --noEmit` clean, `vite build` exit 0 — 149 modules, 540 kB JS (158 kB gzip) in 3.8 s |
| Frontend ↔ API integration | real `runserver` + `vite` dev server | SPA shell 200, CSRF cookie via proxy, login via proxy (`HttpOnly` session), `me` + assignments + choices + transitions fetched, anonymous request → 403 |

### Verified end-to-end over real HTTP (the SPA's own path)

```
1. SPA shell: HTTP 200, #root present, entry /src/main.tsx
2. CSRF via proxy: HTTP 200, csrftoken cookie on the SPA origin
3. Login via proxy: engineer@example.com (ENGINEER), session cookie HttpOnly=true
4. Authenticated data: me + my-assignments(2) + choices(10 statuses, 5 priorities)
5. Workflow: ENG-5 (IN_REVIEW) → "Request changes"  (engineers may request changes, not resolve)
6. Vite dev transforms: main.tsx, router.tsx, TicketDetailPage.tsx, http.ts → HTTP 200
7. Anonymous request to /auth/me/ → 403 (the signal the SPA uses to detect a dead session)
```

### Not verified in this environment (stated explicitly, not glossed over)

* `docker compose up` was never executed: the development machine has the Docker CLI but no running
  daemon (and no Docker Desktop). The compose file is validated as YAML and by `docker compose config`.
* PostgreSQL-only behaviour (`SELECT … FOR UPDATE`, the `inet` column, concurrent key allocation) is
  covered by a test that is **skipped** locally. It has not been executed against a real PostgreSQL.
* Redis/MinIO paths: tests run with eager Celery and filesystem storage.
* **Browser rendering / visual QA**: the SPA was verified as a compiled bundle and through its real
  network path (above), but no browser session was driven by hand or by a headless runner — layout,
  drawer behaviour and focus management at real viewport sizes are unrendered.

See [docs/development/testing-guide.md](docs/development/testing-guide.md) §7 and
[docs/development/deployment-guide.md](docs/development/deployment-guide.md) §11 for the exact list and
how to verify each item.
