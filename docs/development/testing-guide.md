# Testing Guide

## 1. How to run the suite

```bash
cd backend
.venv/Scripts/python -m pytest                 # everything
.venv/Scripts/python -m pytest apps/tickets    # one module
.venv/Scripts/python -m pytest -k workflow     # by name
.venv/Scripts/python -m pytest -m security     # security-annotated tests
.venv/Scripts/python -m pytest -m postgres     # PostgreSQL-only checks
.venv/Scripts/python -m pytest --cov=apps --cov-report=term-missing
```

Configuration lives in `backend/pyproject.toml` (`[tool.pytest.ini_options]`): `DJANGO_SETTINGS_MODULE
= config.settings.test`, `testpaths = ["apps", "tests"]`, `--strict-markers`.

## 2. What the test settings change, and why

| Setting | Test value | Reason |
| --- | --- | --- |
| `DATABASES` | SQLite file | No external services required (ADR-008) |
| `PASSWORD_HASHERS` | MD5 | PBKDF2 would dominate runtime; hashing correctness is Django's concern, not ours |
| `CELERY_TASK_ALWAYS_EAGER` | `True` | Task logic actually executes and is asserted instead of mocked |
| `EMAIL_BACKEND` | locmem | No mail leaves the process |
| `MEDIA_ROOT` | temp directory | Uploads never touch the repository |
| `DEFAULT_THROTTLE_RATES` | `None` | Only the dedicated throttle test re-enables it |

## 3. Layout

Tests live with the module they test (`apps/<module>/tests/`), because a failure should point at the
module whose rule broke. `backend/tests/` holds repository-level structural tests.

```
apps/accounts/tests/       test_auth.py, factories.py
apps/projects/tests/       test_projects.py, test_memberships.py, factories.py
apps/tickets/tests/        test_tickets.py, test_assignment.py, test_ticket_keys.py, factories.py
apps/workflows/tests/      test_workflow.py, test_workflow_matrix.py
apps/comments/tests/       test_comments.py, factories.py
apps/attachments/tests/    test_attachments.py, factories.py
apps/notifications/tests/  test_notifications.py
apps/audit/tests/          test_audit.py
apps/reports/tests/        test_reports.py
tests/                     test_project_structure.py
```

**Factories create data; services enforce rules.** Factories are realistic (a project factory also
creates the owner's MANAGER membership, a ticket factory opens its timeline) so tests never assert
against a state the application could not produce.

## 4. Markers

| Marker | Meaning |
| --- | --- |
| `postgres` | Requires PostgreSQL; auto-skipped on SQLite by a `conftest` hook that prints the reason |
| `security` | Asserts a security property (authorisation, CSRF, upload validation) |
| `slow` | Reserved for tests over ~1s (currently unused) |

The skip hook is deliberate: a test that silently stops testing row locking is worse than no test, so
`-ra` prints exactly which tests were skipped and why.

## 5. Recorded results

Last full run during delivery (2026-11-15, Python 3.14.2, Django 5.2.19, SQLite):

```
$ .venv/Scripts/python -m pytest apps tests -q
........................................................................ [ 31%]
........................................................................ [ 62%]
........................................................................ [ 94%]
s............                                                            [100%]
=========================== short test summary info ===========================
SKIPPED [1] apps\tickets\tests\test_ticket_keys.py:115: requires PostgreSQL (see ADR-008); run with Docker
228 passed, 1 skipped in 7.76s
```

Lint:

```
$ .venv/Scripts/python -m ruff check apps common config tests
All checks passed!
```

Schema:

```
$ .venv/Scripts/python manage.py spectacular --file ../docs/api/openapi.yaml
Schema generation summary:
Warnings: 0 (0 unique)
Errors:   0 (0 unique)
```

## 6. Coverage of the requirements

| Area | Representative tests |
| --- | --- |
| Authentication, sessions, CSRF | `accounts/tests/test_auth.py` (19 tests, incl. CSRF and the inactive-account disclosure rule) |
| Project authorisation | `projects/tests/test_projects.py`, `test_memberships.py` (35 tests) |
| Ticket rules, filtering, ordering | `tickets/tests/test_tickets.py` |
| Key allocation + race handling | `tickets/tests/test_ticket_keys.py` (the deterministic retry test runs everywhere; the threaded test is `postgres`-only) |
| Workflow: every declared and undeclared move | `workflows/tests/test_workflow_matrix.py` (19 declared rules × 3 roles, plus all 71 undeclared pairs) |
| Comments edit/delete rules | `comments/tests/test_comments.py` |
| Upload validation and download authorisation | `attachments/tests/test_attachments.py` |
| Notification audience, dedup, delivery | `notifications/tests/test_notifications.py` |
| Audit immutability and sanitisation | `audit/tests/test_audit.py` |
| Report scoping | `reports/tests/test_reports.py` |
| Structural hazards (module/package shadowing) | `tests/test_project_structure.py` |

## 7. Known unverified items (be precise, not optimistic)

| Item | Why it was not verified | How to verify |
| --- | --- | --- |
| **PostgreSQL-only behaviour**: `SELECT … FOR UPDATE` serialisation, `inet`-backed IP column, expression index behaviour | No PostgreSQL server and no running Docker daemon in this environment | `docker compose up -d db && DB_ENGINE=postgres POSTGRES_HOST=localhost .venv/Scripts/python -m pytest -m postgres -v` |
| **Celery against a real broker** | No Redis locally; tests run eager | `docker compose up -d redis && celery -A config worker` then trigger an assignment and watch the task log |
| **MinIO/S3 storage path** | No MinIO locally | `docker compose up -d minio minio-init` with `STORAGE_BACKEND=s3`, then upload/download an attachment |
| **`docker compose up` end-to-end** | Docker daemon unavailable | Run it; the file passes `docker compose config` (see the deployment guide) |
| **Frontend ↔ backend integration in a browser** | Backend was verified via the API test suite; the browser session was not exercised here | `docker compose up`, log in with a seeded account, walk the flows in §QC checklist |

### Environment observation worth recording

`manage.py seed_demo` originally wrapped its whole run in a single `transaction.atomic()` block. On
SQLite, with this Windows environment, an audit write that followed a project creation inside that
long transaction failed with `OperationalError: unable to open database file` (the same sequence
succeeds in the test database and with a shorter transaction). The command now relies on the
per-service atomicity instead, which is also the better design for a seeding command: progress
survives a failure, locks stay short, and a re-run is idempotent. This is recorded here rather than
silently fixed because the failure mode is environment-specific and has not been explained to the
bottom — it is *not* reproducible in the API request path, where every operation is short.

## 8. Writing a new test

1. Decide which rule you are protecting, and put the test in the module that owns it.
2. Build only the object graph the rule needs (`team` fixture covers the common role matrix).
3. Prefer the **service** for business rules and the **API** for HTTP contracts (status codes, error
   envelope, permission visibility).
4. Assert the observable consequence (status changed, history row exists, audit action recorded), not
   the implementation (`save` was called).
5. If the behaviour depends on PostgreSQL locking, mark it `postgres` instead of weakening it.