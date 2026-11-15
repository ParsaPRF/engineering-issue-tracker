# System Overview — Engineering Issue & Ticket Tracking System

## 1. Product in one paragraph

A web application that lets engineering organisations manage **projects**, report **issues**, turn
them into **tickets**, assign them to **engineers**, move them through a **controlled lifecycle**,
collaborate with **comments and attachments**, and observe everything through a **dashboard**,
**notifications**, and an **immutable audit trail**. Multiple projects and multiple users with
different permissions coexist in one deployment.

## 2. Actors

| Actor | Kind | Description |
| --- | --- | --- |
| Admin | System role | Operates the installation: users, roles, all projects, audit access. |
| Project Manager | System role, usually also project member | Owns projects, plans work, triages and assigns tickets. |
| Engineer | System role | Works tickets assigned to them, comments, attaches evidence, transitions work states. |
| Reporter | System role | Reports issues, comments, follows up on their own tickets. |

A user's effective capability is `system role` **AND** `membership in the specific project`
(see `module-responsibilities.md` and ADR-012). A global Admin is the only role that does not
need a membership row.

## 3. Runtime topology (development)

```
+---------------------------------------------------------------------------+
|                            Browser (SPA)                                  |
|   React 19 + TypeScript + Vite  ->  http://localhost:5173                 |
+---------------------------------+-----------------------------------------+
                                  |  fetch(credentials: 'include')
                                  |  X-CSRFToken header (session auth)
                                  v
+---------------------------------------------------------------------------+
|  Nginx (prod)  /  Vite dev-server proxy (dev)                             |
+---------------------------------+-----------------------------------------+
                                  v
+---------------------------------------------------------------------------+
|  Django 5.2 + Django REST Framework   (modular monolith, /api/v1/)        |
|                                                                           |
|   apps/accounts   apps/projects   apps/tickets   apps/workflows           |
|   apps/comments   apps/attachments apps/notifications apps/audit          |
|   apps/reports                                                            |
|                                                                           |
|   API layer -> services (writes) -> selectors (reads) -> ORM              |
+------+---------------------------+--------------------------+-------------+
       |                           |                          |
       v                           v                          v
+--------------+        +--------------------+       +----------------------+
| PostgreSQL   |        | Redis              |       | MinIO / S3           |
| (data)       |        | broker + cache     |       | attachment objects   |
+--------------+        +---------+----------+       +----------------------+
                                  v
                        +--------------------+
                        | Celery worker      |
                        | notifications,     |
                        | async fan-out      |
                        +--------------------+
```

## 4. Layering rules (enforced by review, described in ADR-004)

| Layer | Lives in | May do | Must not do |
| --- | --- | --- | --- |
| Presentation | `apps/*/api/` | parse/validate input, call services/selectors, shape output | contain business rules or multi-step writes |
| Application / Service | `apps/*/services/` | orchestrate business operations, own transactions, emit audit + notifications | know about HTTP, request objects, or serializers |
| Query / Selector | `apps/*/selectors/` | reusable, permission-aware read queries with `select_related`/`prefetch_related` | mutate state |
| Data access | `apps/*/models/` | schema, invariants that hold for a single row, small helpers | cross-module orchestration |
| Platform | `common/` | base models, mixins, pagination, exception handling, permissions helpers | business rules of a specific module |

Dependency direction is one-way: `api -> services -> selectors/models`. Cross-module calls go
through the other module's **service or selector functions**, never through its models from a
sibling API layer, and never as an import cycle (`tickets` imports `workflows.services`;
`workflows` receives ticket instances as arguments instead of importing ticket selectors).

## 5. Request lifecycle example (status transition)

1. `POST /api/v1/tickets/<uuid>/transitions/` with `{"to_status": "IN_PROGRESS", "comment": "..."}`.
2. `TicketTransitionSerializer` validates the *shape* of the payload only.
3. The view calls `workflows.services.transition_ticket(ticket=..., to_status=..., actor=request.user, comment=...)`.
4. The service: loads the ticket inside `transaction.atomic()` with `select_for_update`,
   asks `workflows.state_machine.can_transition(current, target)`, checks the actor's permission
   via `projects.permissions.can_transition_ticket(...)`, applies side effects
   (`assignee` requirement, `resolved_at` stamp), writes `TicketStatusHistory`, writes `AuditEvent`,
   and schedules a notification.
5. The view serialises the updated ticket and returns `200`.

Steps 4 is the only place where a status can change. There is no writable `status` field in
`TicketSerializer` (ADR-005) — attempted writes are rejected, not silently ignored.

## 6. Non-goals for v1 (explicit)

* Microservices, event streaming, CQRS read models.
* Real-time websockets (polling/refetch is enough at this scale).
* Multi-tenancy beyond project-level isolation.
* Time tracking / sprint planning / burndown charts.
* OAuth/SSO providers (the session layer is designed so it can be added later).
