# Non-Functional Requirements

## NFR-1 Security

| ID | Requirement | How it is met |
| --- | --- | --- |
| NFR-1.1 | Authentication is required for every endpoint except registration, login, schema/docs, and health. | DRF `DEFAULT_PERMISSION_CLASSES = IsAuthenticated`; explicit `AllowAny` opt-ins. |
| NFR-1.2 | Authorisation is checked at the object level, not only at the endpoint level. | `projects/permissions.py` predicates called from API permissions **and** services. |
| NFR-1.3 | Cross-project access must fail closed, and must not confirm existence of foreign objects. | Querysets are always pre-scoped to visible projects; foreign objects return `404`. |
| NFR-1.4 | CSRF protection is enabled for session-authenticated unsafe requests. | DRF `SessionAuthentication` + `X-CSRFToken` from the CSRF cookie. |
| NFR-1.5 | CORS is an explicit allow-list with credentials, never `*`. | `CORS_ALLOWED_ORIGINS` from env; `CORS_ALLOW_CREDENTIALS = True`. |
| NFR-1.6 | Secrets come from the environment; no credential is committed. | `django-environ`, `.env.example` with placeholders only, `.gitignore` covers `.env`. |
| NFR-1.7 | Passwords use a modern hasher and Django's validators. | Default PBKDF2 hasher (Argon2 optional), `AUTH_PASSWORD_VALIDATORS`. |
| NFR-1.8 | Uploads are validated by extension, content type and size, and stored under random names. | `attachments/validators.py`; storage key is a UUID + safe extension. |
| NFR-1.9 | File downloads are never public URLs. | Authorising download view; private bucket. |
| NFR-1.10 | Errors never leak stack traces, SQL, or secrets in production. | `DEBUG=False`, normalised error envelope, generic `500` message. |
| NFR-1.11 | Rate limits protect login and registration. | DRF `ScopedRateThrottle` on auth endpoints. |
| NFR-1.12 | Production cookies are `Secure`, `HttpOnly`, `SameSite=Lax`; HSTS and HTTPS redirect enabled. | `config/settings/production.py`. |
| NFR-1.13 | Status transitions cannot be forged through a generic update. | ADR-005; `status` read-only in serializers; transition service only writer. |

## NFR-2 Performance and scalability

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-2.1 | Ticket list endpoint responds within 300 ms at 10k tickets/project. | Indexed filters, pagination, no N+1. |
| NFR-2.2 | No N+1 queries on list/detail endpoints. | `select_related`/`prefetch_related` in selectors; asserted in tests with `assertNumQueries`. |
| NFR-2.3 | Pagination is mandatory on all list endpoints. | `PageNumberPagination`, page size 25, max 100. |
| NFR-2.4 | Long or fan-out work does not run inside the request. | Celery + Redis for notifications. |
| NFR-2.5 | Dashboard aggregates run as a bounded number of grouped queries, not per-row loops. | `values().annotate()` aggregation in `reports/selectors.py`. |

## NFR-3 Reliability

| ID | Requirement |
| --- | --- |
| NFR-3.1 | Multi-row invariants (status + history + audit) are atomic. |
| NFR-3.2 | Notification processing is idempotent under at-least-once delivery. |
| NFR-3.3 | Ticket key allocation is safe under concurrent creation (ADR-007). |
| NFR-3.4 | Health endpoints report application and dependency liveness. |
| NFR-3.5 | Services and Celery containers define docker-compose health checks. |

## NFR-4 Maintainability

| ID | Requirement |
| --- | --- |
| NFR-4.1 | No business logic in views or serializers; enforced by review and by tests targeting services directly. |
| NFR-4.2 | Modules communicate only through services/selectors, one-way dependencies, no import cycles. |
| NFR-4.3 | Type hints on all service/selector functions; `ruff` clean (lint + import order). |
| NFR-4.4 | Every module has tests; the suite runs with a single command. |
| NFR-4.5 | Documentation in `docs/` matches the implementation and is updated in the same change. |

## NFR-5 Testability

| ID | Requirement |
| --- | --- |
| NFR-5.1 | The full domain suite runs with `pytest` and no external services (SQLite + eager Celery). |
| NFR-5.2 | Object factories exist for every model used in tests. |
| NFR-5.3 | Authorisation is tested per role and for cross-project access. |
| NFR-5.4 | Both valid and invalid workflow transitions are covered. |
| NFR-5.5 | PostgreSQL-specific behaviour is covered by tests marked `postgres`, skipped elsewhere. |

## NFR-6 Usability and accessibility

| ID | Requirement |
| --- | --- |
| NFR-6.1 | Responsive layout usable from 360 px to 1920 px. |
| NFR-6.2 | Every list/table has explicit loading, empty and error states. |
| NFR-6.3 | Forms show field-level errors from both client and server validation. |
| NFR-6.4 | Interactive controls are keyboard reachable with visible focus; colour is never the only signal (status/priority also carry text). |
| NFR-6.5 | API error messages are actionable ("An assignee is required before starting work"), not internal codes alone. |

## NFR-7 Operability and deployment

| ID | Requirement |
| --- | --- |
| NFR-7.1 | `docker compose up` starts backend, frontend, PostgreSQL, Redis, Celery worker, MinIO and Nginx. |
| NFR-7.2 | Database data and object storage survive container restarts via named volumes. |
| NFR-7.3 | Configuration is 12-factor: everything environment-driven, sane non-secret defaults. |
| NFR-7.4 | Migrations are applied by an explicit release step, never automatically on container boot in production. |
| NFR-7.5 | Deployment guide documents TLS, static files, backups, and audit-table hardening. |
| NFR-7.6 | Readiness is verifiable: health endpoint, `/api/docs/`, and a smoke-test command. |

## NFR-8 Compatibility and constraints

| ID | Requirement |
| --- | --- |
| NFR-8.1 | Python 3.12+ (developed and verified on 3.14.2); Django 5.2 LTS. |
| NFR-8.2 | PostgreSQL 16+ in Docker/production; SQLite permitted only for local development and the default test run (ADR-008). |
| NFR-8.3 | Node 20+ for the frontend (developed on Node 24). |
| NFR-8.4 | Modern evergreen browsers; no IE support. |
| NFR-8.5 | Timestamps stored in UTC, rendered in the browser's time zone. |
