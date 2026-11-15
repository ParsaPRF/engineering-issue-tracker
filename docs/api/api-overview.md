# API Overview

Base path: **`/api/v1`**. Generated OpenAPI 3 schema: [`openapi.yaml`](openapi.yaml).
Interactive docs while the server runs: `/api/docs/` (Swagger UI) and `/api/redoc/` (ReDoc).

## 1. Authentication

Session-based, **not** JWT (ADR-003). The session id lives in an `HttpOnly` cookie, so JavaScript
cannot read it; the CSRF token is deliberately readable because the SPA has to echo it.

```
1. GET  /api/v1/auth/csrf/            → Set-Cookie: csrftoken=...   (call once per page load)
2. POST /api/v1/auth/login/           → Set-Cookie: sessionid=...; HttpOnly
       {"email": "...", "password": "..."}
3. every unsafe request               → header: X-CSRFToken: <csrftoken value>
       fetch(url, {credentials: "include", method: "POST", headers: {"X-CSRFToken": token}})
4. GET  /api/v1/auth/me/              → the current user + their project roles
5. POST /api/v1/auth/logout/          → 204, server-side session destroyed
```

Status codes you must expect:

| Situation | Status | Notes |
| --- | --- | --- |
| Missing/invalid credentials on a protected endpoint | **403** | Session authentication has no `WWW-Authenticate` challenge, so DRF reports "not authenticated" as 403. |
| Wrong password | **400** `invalid_credentials` | Deliberately indistinguishable from an unknown email. |
| Correct password, deactivated account | **403** `account_inactive` | Safe to disclose: the caller proved they hold the credential. |
| Missing/incorrect CSRF token on an unsafe request | **403** | Produced by Django's CSRF layer (an HTML body, not the JSON envelope). |
| Rate limit exceeded (login/register) | **429** `throttled` | Scoped throttle, `20/min` by default. |

## 2. Error envelope

Every API error has the same shape:

```json
{
  "error": {
    "code": "invalid_transition",
    "detail": "Cannot move a ticket from RESOLVED to TRIAGED.",
    "fields": {"to_status": ["..."]}
  }
}
```

`fields` is present only for validation errors. `code` is stable and intended for programmatic
branching; `detail` is meant for humans. Codes used across the API:

| Code | Meaning |
| --- | --- |
| `validation_error` | Payload shape is wrong (see `fields`) |
| `not_found` | Object missing **or not visible** to the caller (never 403 for foreign objects) |
| `permission_denied` | Caller is a project member but lacks the capability for this action |
| `invalid_credentials` / `account_inactive` | Login outcomes |
| `email_taken` / `registration_disabled` | Registration outcomes |
| `duplicate_project_key` / `duplicate_component_name` | Uniqueness inside a project |
| `inactive_user` / `ineligible_assignee` / `ineligible_lead` | Assignment eligibility rules |
| `project_archived` | Archived projects accept no new tickets |
| `invalid_component` / `inactive_component` / `invalid_labels` | Cross-entity references |
| `field_not_editable` | Your role may not change that ticket field |
| `use_transition_endpoint` / `use_assignment_endpoint` | Status/assignee must go through their own operation |
| `invalid_status` / `invalid_transition` / `noop_transition` | Workflow rejections |
| `transition_not_permitted` | The move exists, your project role may not perform it |
| `comment_required` / `assignee_required` | Transition preconditions |
| `last_manager` / `owner_must_be_manager` / `owner_cannot_be_removed` | Project membership invariants |
| `already_archived` / `not_archived` / `already_inactive` / `already_deleted` | Idempotency-ish state errors |
| `attachment_too_large` / `unsupported_file_type` / `dangerous_file_type` / `empty_attachment` | Upload validation |
| `edit_window_closed` | Comment edit window (default 30 min) |
| `ticket_key_allocation_failed` | Rare: concurrent key allocation exhausted its retries (retry the request) |
| `throttled` | Rate limited |

## 3. Pagination

All list endpoints are paginated:

```json
{"count": 132, "total_pages": 6, "page": 1, "page_size": 25,
 "next": "…?page=2", "previous": null, "results": [ … ]}
```

`?page_size=` is capped at **100** (NFR-2.3).

## 4. Endpoints

### Authentication and identity (`apps/accounts`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/auth/csrf/` | Set the CSRF cookie |
| POST | `/auth/register/` | Register (REPORTER role); 403 if self-registration is disabled |
| POST | `/auth/login/` | Start a session (CSRF protected) |
| POST | `/auth/logout/` | End the session |
| GET/PATCH | `/auth/me/` | Read / update own name and profile |
| POST | `/auth/me/password/` | Change password (invalidates other sessions) |
| GET | `/auth/users/` | **Admin** paginated user list |
| GET | `/auth/users/directory/?search=` | Admin/PM people search (bounded to 20) |
| POST | `/auth/users/{id}/activate/` · `/deactivate/` | **Admin** activation |
| PATCH | `/auth/users/{id}/role/` | **Admin** system role change |

### Projects (`apps/projects`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/projects/` | List (scoped) / create (Admin+PM) |
| GET/PATCH | `/projects/{id}/` | Detail / update (managers) |
| POST | `/projects/{id}/archive/` · `/restore/` | Lifecycle (no delete endpoint exists) |
| GET/POST | `/projects/{id}/members/` | List / add member |
| PATCH/DELETE | `/projects/{id}/members/{membership_id}/` | Change role / remove (deactivate) |
| GET/POST | `/projects/{id}/components/` | List / create component |
| GET | `/projects/{id}/stats/` | Ticket statistics for the project |
| GET | `/components/{id}/` | Component detail |
| PATCH | `/components/{id}/` | Update component |
| POST | `/components/{id}/deactivate/` | Retire component (tickets keep the reference) |

### Tickets (`apps/tickets`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/tickets/` | List with filtering/search/ordering (see below) |
| POST | `/tickets/` | Create (key allocated server-side) |
| GET | `/tickets/{id}/` | Detail (description, labels, counts) |
| PATCH | `/tickets/{id}/` | Update permitted fields (`status`/`assignee` rejected) |
| POST | `/tickets/{id}/assign/` | Assign / reassign / unassign (`{"assignee": uuid|null}`) |
| GET | `/tickets/my-assignments/` | My open tickets (`?include_done=true`) |
| GET | `/tickets/choices/` | Enumerations for forms |
| GET/POST | `/labels/` | List / create project labels |

**Ticket list query parameters**

`project`, `status` (comma-separated), `type`, `priority`, `severity`, `assignee`, `reporter`,
`component`, `label` (name or id), `unassigned`, `overdue`, `open_only`, `due_before`, `due_after`,
`created_after`, `created_before`, `search` (key/title/description), `ordering`
(`created_at`, `updated_at`, `priority`, `severity`, `due_date`, `status`, `key`, `title`; prefix `-`
for descending), `page`, `page_size`.

`ordering=priority` is **semantic** (CRITICAL first), not alphabetical — it is backed by a numeric
rank annotation.

### Workflow (`apps/workflows`)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/tickets/{id}/transitions/` | `{"to_status": "...", "comment": "..."}` — the only way to change status |
| GET | `/tickets/{id}/history/` | The status timeline |
| GET | `/workflows/transitions/?ticket={id}` | Legal moves for this ticket **and this caller** |
| GET | `/workflows/` | The whole lifecycle catalogue |

`GET /workflows/transitions/?ticket=…` is what the UI renders buttons from:

```json
{
  "ticket_id": "…",
  "current_status": "TRIAGED",
  "allowed": [
    {"from_status": "TRIAGED", "to_status": "IN_PROGRESS", "label": "Start work",
     "requires_comment": false, "requires_assignee": true,
     "blocked_by": ["assignee_required"], "available": false}
  ]
}
```

### Collaboration (`apps/comments`, `apps/attachments`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/tickets/{id}/comments/` | List / add a comment |
| GET/PATCH/DELETE | `/comments/{id}/` | Read / edit (author, within window) / soft delete |
| GET/POST | `/tickets/{id}/attachments/` | List / upload (`multipart`, field `file`) |
| POST | `/comments/{id}/attachments/` | Upload attached to a comment |
| GET | `/attachments/{id}/download/` | **Authorised** file download (no public URLs, ever) |
| DELETE | `/attachments/{id}/` | Soft delete + remove the stored object |

### Notifications (`apps/notifications`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/notifications/` | My inbox (`?unread=true`) |
| GET | `/notifications/unread-count/` | `{"unread": n}` for the bell badge |
| POST | `/notifications/{id}/read/` | Mark one read |
| POST | `/notifications/read-all/` | Mark all read |

### Reports (`apps/reports`, read-only)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/reports/dashboard/` | Totals + breakdowns (`?project=<uuid>` repeatable) |
| GET | `/reports/workload/` | Open tickets per engineer |
| GET | `/reports/my-workload/` | The caller's own summary |
| GET | `/reports/recent-activity/?limit=` | Audit feed scoped to visible projects |
| GET | `/reports/projects/` | Project options with counters |

### Audit (`apps/audit`, read-only)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/audit/` | **Admin only**, paginated, filters `action`, `object_type`, `project`, `ticket`, `actor` |

No endpoint can create, update or delete an audit event (FR-8.3).

### Operational

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health/` | Liveness/readiness probe (unauthenticated, no business data) |
| GET | `/api/schema/` | OpenAPI 3 YAML |
| GET | `/api/docs/` · `/api/redoc/` | Swagger UI / ReDoc |

## 5. Conventions

* **UUIDs** in URLs and payloads; ticket keys (`ENG-1042`) are human identifiers, not lookup keys.
* **Dates** are ISO-8601; `due_date` is a date, timestamps are UTC (`…Z` or `+00:00`).
* **Foreign objects return 404, not 403** — existence is not confirmed to non-members (NFR-1.3).
* **No endpoint accepts `status` as a writable field.** Sending it is an error, not a silent no-op.
* **`reporter` is never taken from the payload**; it is the authenticated user.
* **Attachments never expose a storage URL**; `download_url` points at the authorising endpoint.

## 6. Example session (curl)

```bash
BASE=http://127.0.0.1:8000
# CSRF cookie + login
curl -s -c jar.txt "$BASE/api/v1/auth/csrf/"
TOKEN=$(grep csrftoken jar.txt | awk '{print $7}')
curl -s -b jar.txt -c jar.txt -H "X-CSRFToken: $TOKEN" -H "Content-Type: application/json" \
     -d '{"email":"engineer@example.com","password":"Demo!Passw0rd"}' "$BASE/api/v1/auth/login/"
# my assignments
curl -s -b jar.txt "$BASE/api/v1/tickets/my-assignments/"
# what can I do next with this ticket?
curl -s -b jar.txt "$BASE/api/v1/workflows/transitions/?ticket=<uuid>"
```