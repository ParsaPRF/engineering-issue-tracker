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

Implementation follows the nine phases in the project brief. Phase-by-phase verification results
(including anything that could **not** be verified in this environment) are reported in
[docs/development/testing-guide.md](docs/development/testing-guide.md) and in the final delivery
report. Nothing is marked complete merely because files exist: each phase ends with executed
commands and their real output.
