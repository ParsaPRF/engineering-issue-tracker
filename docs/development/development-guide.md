# Development Guide

## 1. Prerequisites

| Tool | Version used | Notes |
| --- | --- | --- |
| Python | 3.14.2 | 3.12+ works; Django 5.2 supports 3.10–3.14 |
| Node.js | 24.18 | 20+ is enough for Vite |
| pnpm | 12.15 | `corepack enable` provides it |
| PostgreSQL | 17 (Docker) | Optional locally: SQLite is a documented fallback (ADR-008) |
| Redis | 7 (Docker) | Optional locally: Celery runs eagerly |
| Docker | 29 (CLI) | Needed only for the compose stack |

## 2. First-time backend setup

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate on Unix

# Fast path (this is what was used to build the project):
uv pip install --python .venv/Scripts/python.exe -r requirements/development.txt
# Standard path (slower; pip's resolver struggled with the unpinned set on this machine):
#   pip install -r requirements/development.txt

cp ../.env.example ../.env        # then edit; for a local run set DB_ENGINE=sqlite
python manage.py migrate
python manage.py seed_demo        # optional: demo users/projects/tickets
python manage.py runserver
```

Then: API <http://127.0.0.1:8000/api/docs/>, health <http://127.0.0.1:8000/health/>.

Devices without Redis: keep `CELERY_TASK_ALWAYS_EAGER=True` in `.env` so notification tasks run
inline. With Redis available, set it to `False` and run `celery -A config worker -l info`.

## 3. First-time frontend setup

```bash
cd frontend
pnpm install
pnpm dev        # http://127.0.0.1:5173, proxies /api and /media to :8000
pnpm build      # production bundle; also runs tsc
```

The Vite dev server proxies the API, so the browser sees a **single origin** — which is what makes
cookie authentication work without CORS gymnastics.

## 4. Repository map

```
backend/
  config/               settings/{base,development,production,test}.py, urls, celery, wsgi/asgi
  apps/<module>/        models, services/, selectors/, api/, permissions, tests/
  common/               abstract models, permissions, pagination, exceptions, uuid, views, choices
  tests/                repository-level structural tests
  requirements/         base.txt, development.txt, production.txt (all pinned)
  pyproject.toml        pytest + ruff configuration
frontend/               React + TypeScript + Vite SPA
docker/                 Dockerfiles, entrypoint, nginx.conf
docs/                   architecture, requirements, api, development, learning
docker-compose.yml      full stack
```

## 5. Layering rules you must not break

```
api/  →  services/  →  selectors/ + models/
```

| Layer | May | Must not |
| --- | --- | --- |
| `api/` | validate shape, call services/selectors, choose status codes | contain business rules, multi-step writes, or permission logic |
| `services/` | own transactions, raise `DomainError` subclasses, write audit + notifications | import DRF, know about `request` bodies, or return `Response` |
| `selectors/` | permission-scoped read queries with joins | mutate state |
| `models/` | schema + single-row invariants | orchestrate other modules |

Dependency direction is one-way. `projects.permissions` is the kernel every module calls; `workflows`
receives its rules as arguments so `projects` never imports it; `reports` sits on top and is imported
by nothing at module level.

## 6. How to add a feature (checklist)

1. **Model change** → edit the model, `python manage.py makemigrations <app>`, review the migration
   (indexes, constraints, `on_delete`), then `migrate`.
2. **Business rule** → a function in `services/`, raising `InvariantViolation` / `AccessDenied` with a
   stable `code` and a human message. Permission check *inside* the service.
3. **Read path** → a function in `selectors/` that starts from a permission-scoped queryset and uses
   `select_related`/`prefetch_related`.
4. **HTTP surface** → serializer for shape only, view calls the service/selector, `@extend_schema`
   for the docs.
5. **Audit** → one `audit_record(...)` call with small metadata (never a request body).
6. **Notification** (if a human must know) → `notify_*(...)` helper with a dedup suffix.
7. **Tests** → service test for the rule, API test for the contract, authorisation test for the
   cross-project case.
8. **Docs** → update `docs/api/api-overview.md` and, if the architecture moved,
   `docs/architecture/architecture-decisions.md`.

## 7. Pitfalls this codebase already tripped over (read before debugging)

1. **Module/package shadowing.** A directory `apps/x/services/` containing only `__init__.py` silently
   shadows `apps/x/services.py`, and the error appears at the *caller* as `ImportError: cannot import
   name …`. Guarded by `tests/test_project_structure.py` — run it after adding files.
2. **`Choices.values` is a property, not a method** (Django 5+). Defining a `values()` classmethod in a
   `TextChoices` subclass does not win against the metaclass property; use `TicketStatus.values` and
   add only genuinely new helpers (`common/choices.py`).
3. **Filtering a multi-valued relation and counting it in the same query.** `filter(memberships__user=…)
   .annotate(Count("memberships"))` reuses the join and reports 1. Use an `Exists(OuterRef("pk"))`
   predicate instead (`projects/selectors/projects.py`).
4. **DRF runs field validators before `validate_<field>`.** A regex validator on a `key` field rejects
   `"eng"` before your normaliser can upper-case it. Normalise first, then validate.
5. **`APIView` is CSRF-exempt and `SessionAuthentication` only enforces CSRF for authenticated users.**
   Anonymous login/registration need an explicit `@method_decorator(csrf_protect, name="dispatch")`.
6. **Sorting a CharField of priorities sorts alphabetically** (`CRITICAL` < `LOW`). Use a rank
   annotation and a custom `OrderingFilter` (tickets/api/filters.py).
7. **factory_boy `post_generation` runs after INSERT**, so it cannot fill a `NOT NULL` FK column;
   declare the FK as a `SubFactory` and use the hook only for related rows.
8. **`select_for_update()` has no effect on SQLite.** Concurrency tests are marked `postgres` instead
   of being weakened.
9. **A soft-deleted row still resolves by primary key.** Every read path that serves the row
   (`attachments.selectors.get_visible_attachment`) must filter `is_deleted=False`, not only the list
   endpoint — an actual bug the test suite caught.

## 8. Code quality commands

```bash
cd backend
.venv/Scripts/python -m ruff check apps common config tests     # lint + import order
.venv/Scripts/python -m ruff check --fix apps common config tests
.venv/Scripts/python -m pytest -q                              # tests
.venv/Scripts/python manage.py check                           # Django system checks
.venv/Scripts/python manage.py spectacular --file ../docs/api/openapi.yaml   # schema must stay clean
.venv/Scripts/python manage.py makemigrations --check --dry-run               # no unmade migrations
```

The last two are the ones to run before every commit: a clean schema and no pending migrations are
cheap checks that catch most integration regressions.

## 9. Environment variables

See `.env.example` (the single source of truth). The important groups:

| Group | Variables |
| --- | --- |
| Django | `DJANGO_SETTINGS_MODULE`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Database | `DB_ENGINE`, `POSTGRES_*`, `SQLITE_PATH` |
| Cache/broker | `CACHE_BACKEND`, `CACHE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_TASK_ALWAYS_EAGER` |
| Storage | `STORAGE_BACKEND`, `AWS_*` |
| Rules | `TICKET_KEY_MAX_RETRIES`, `COMMENT_EDIT_WINDOW_MINUTES`, `ATTACHMENT_MAX_BYTES`, `ATTACHMENT_ALLOWED_EXTENSIONS`, `ALLOW_SELF_REGISTRATION` |
| Frontend | `VITE_API_BASE_URL` |

`.env` is git-ignored; `.env.example` contains placeholders only.