# Functional Requirements

Requirement IDs are stable and referenced from tests and the API overview.

## FR-1 Identity and access

| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-1.1 | A visitor can register with email, full name and password; the account defaults to system role `REPORTER` and `is_active = True`. | `tests/integration/test_auth.py` |
| FR-1.2 | Login uses session authentication; the response sets an `HttpOnly` session cookie and the SPA sends `X-CSRFToken` on unsafe methods. | `test_auth.py`, `test_csrf.py` |
| FR-1.3 | Logout destroys the server-side session. | `test_auth.py` |
| FR-1.4 | `GET /api/v1/auth/me/` returns the current user, system role, and the projects they belong to with their per-project role. | `test_auth.py` |
| FR-1.5 | A user can update their own profile (full name, job title, phone, timezone, notification preferences) but **not** their system role. | `test_accounts.py` |
| FR-1.6 | Only an Admin can change another user's system role or activation state. | `test_accounts.py` |
| FR-1.7 | A deactivated user cannot authenticate; existing sessions stop working. | `test_accounts.py` |
| FR-1.8 | Passwords are stored with Django's default hasher; minimum length and common-password checks apply. | `test_accounts.py` |

## FR-2 Projects

| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-2.1 | An Admin or Project Manager can create a project with a unique uppercase key, name, description; the creator becomes owner and an active `MANAGER` member. | `test_projects.py` |
| FR-2.2 | Project keys are unique case-insensitively; duplicates are rejected with `400`. | `test_projects.py` |
| FR-2.3 | A project can be updated by its owner, project managers, or an Admin. | `test_projects.py` |
| FR-2.4 | Projects are archived, not deleted; archived projects reject new tickets but stay readable. | `test_projects.py` |
| FR-2.5 | Managers/Admins can add members, change their project role, or deactivate membership. | `test_memberships.py` |
| FR-2.6 | Components can be created/updated per project; names are unique within a project; a component's lead must be a project member. | `test_components.py` |
| FR-2.7 | A user only ever sees projects they are an active member of, unless they are an Admin. | `test_project_authorization.py` |
| FR-2.8 | `GET /api/v1/projects/<id>/stats/` returns ticket totals for that project to those who may view it. | `test_reports.py` |

## FR-3 Tickets

| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-3.1 | A project member can create a ticket of type BUG/TASK/FEATURE/CHANGE_REQUEST/SUPPORT with title, description, priority, severity, optional component, assignee and due date. | `test_tickets.py` |
| FR-3.2 | The ticket key is generated server-side as `PROJECTKEY-N`, unique system-wide, and is immutable after creation. | `test_ticket_keys.py` |
| FR-3.3 | Concurrent ticket creation in the same project never produces a duplicate key. | `test_ticket_keys.py` (PostgreSQL-only test) |
| FR-3.4 | The reporter is always the authenticated creator and cannot be spoofed through the payload. | `test_tickets.py` |
| FR-3.5 | `status` cannot be set or changed through create/update endpoints; the field is read-only. | `test_tickets.py` |
| FR-3.6 | A ticket's component must belong to the ticket's project; the assignee must be an active project member. | `test_tickets.py` |
| FR-3.7 | Ticket list supports filtering (project, status, type, priority, severity, assignee, reporter, component, label, overdue), full-text-ish search (key, title, description), and ordering. | `test_tickets_api.py` |
| FR-3.8 | A ticket is readable by active project members and Admins only; other users receive `404` (not `403`) so existence is not leaked. | `test_ticket_authorization.py` |
| FR-3.9 | Reporters may edit title/description of the tickets they reported while not `CLOSED`; engineers/managers may edit working fields; `key`, `project`, `reporter`, `created_at` are immutable. | `test_tickets.py` |

## FR-4 Assignment

| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-4.1 | A manager or Admin can assign/reassign a ticket to any active project member with role ENGINEER or MANAGER. | `test_assignment.py` |
| FR-4.2 | An engineer can self-assign an unassigned ticket in their project. | `test_assignment.py` |
| FR-4.3 | Assignment changes are recorded in the audit trail and produce a notification for the new assignee. | `test_assignment.py` |
| FR-4.4 | `GET /api/v1/tickets/my-assignments/` lists active tickets assigned to the current user. | `test_assignment.py` |

## FR-5 Workflow

| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-5.1 | Status changes happen only through `POST /api/v1/tickets/<id>/transitions/`. | `test_workflow.py` |
| FR-5.2 | The transition table in `docs/architecture/workflow.md` is enforced exactly: every listed move succeeds for the listed roles, and every unlisted move returns `400 invalid_transition`. | `test_workflow.py`, `test_workflow_matrix.py` |
| FR-5.3 | Transitions requiring a comment reject an empty comment. | `test_workflow.py` |
| FR-5.4 | Transitions requiring an assignee reject tickets without one. | `test_workflow.py` |
| FR-5.5 | Every accepted transition appends a `TicketStatusHistory` row with previous status, new status, actor, timestamp and comment. | `test_workflow_history.py` |
| FR-5.6 | Entering `RESOLVED`/`CLOSED` stamps the matching timestamp; reopening clears it. | `test_workflow.py` |
| FR-5.7 | A transition by a user without project access returns `404`; a transition by a member whose role is not permitted returns `403`; an illegal move returns `400`. | `test_workflow_authorization.py` |
| FR-5.8 | `GET /api/v1/tickets/<id>/history/` and `/transitions/` expose history and currently allowed moves to authorised users. | `test_workflow_history.py` |

## FR-6 Collaboration

| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-6.1 | Project members can comment on tickets; comments show author and timestamp. | `test_comments.py` |
| FR-6.2 | Authors can edit their comment within the edit window; the edit is timestamped. | `test_comments.py` |
| FR-6.3 | Authors can delete their own comment (soft delete); managers/Admins can moderate any comment. | `test_comments.py` |
| FR-6.4 | New comments notify the reporter, assignee and managers, excluding the commenter. | `test_notifications.py` |
| FR-6.5 | Files can be attached to a ticket or comment within the size limit and allow-list. | `test_attachments.py` |
| FR-6.6 | Rejected uploads (bad type, oversized, empty) return `400` and leave no stored object. | `test_attachments.py` |
| FR-6.7 | Attachments are downloadable only through an authorising endpoint; a non-member gets `404`. | `test_attachments.py` |
| FR-6.8 | Deleting an attachment removes the metadata and the stored object. | `test_attachments.py` |

## FR-7 Notifications

| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-7.1 | Notifications are created for: ticket created, assigned, reassigned, status changed, comment added, resolved, reopened. | `test_notifications.py` |
| FR-7.2 | Delivery is asynchronous through Celery; the request path never blocks on it. | `test_notifications.py` |
| FR-7.3 | Re-processing the same notification does not create duplicates (unique `dedup_key`). | `test_notifications.py` |
| FR-7.4 | Users can list their notifications, see an unread count, and mark one or all as read. | `test_notifications_api.py` |
| FR-7.5 | A user can never read or mark another user's notification. | `test_notifications_api.py` |

## FR-8 Audit

| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-8.1 | Audit events are recorded for authentication events, project create/update/archive, membership and role changes, ticket create/update/assign, status transitions, comments, attachments and permission changes. | `test_audit.py` |
| FR-8.2 | An audit event stores actor, action, object type/id, related project/ticket, IP and user agent, and timestamp. | `test_audit.py` |
| FR-8.3 | The audit API is read-only for Admins; no endpoint creates, edits or deletes events. | `test_audit_api.py` |
| FR-8.4 | The audit payload never contains passwords, tokens, or full request bodies. | `test_audit.py` |

## FR-9 Reporting and dashboard

| ID | Requirement | Verified by |
| --- | --- | --- |
| FR-9.1 | `GET /api/v1/reports/dashboard/` returns total, open, resolved, closed and blocked ticket counts for the projects the user can see. | `test_reports.py` |
| FR-9.2 | The dashboard returns breakdowns by priority, severity, type and project. | `test_reports.py` |
| FR-9.3 | `GET /api/v1/reports/workload/` returns open ticket counts per engineer, scoped to visible projects. | `test_reports.py` |
| FR-9.4 | `GET /api/v1/reports/recent-activity/` returns recent audit events scoped to the user's projects. | `test_reports.py` |
| FR-9.5 | Aggregates never include tickets from projects the user cannot access. | `test_reports_authorization.py` |

## FR-10 Frontend

| ID | Requirement |
| --- | --- |
| FR-10.1 | Login page authenticates against the session API and stores no token in JS-accessible storage. |
| FR-10.2 | Protected routes redirect unauthenticated users to login and preserve the intended destination. |
| FR-10.3 | Screens: dashboard, projects list, project detail, ticket list, ticket create, ticket detail, my assignments, team, notifications, reports, profile. |
| FR-10.4 | Ticket detail shows info, status, priority, severity, reporter, assignee, comments, attachments and activity history. |
| FR-10.5 | Status buttons are generated from `GET /transitions/`, comments show validation errors from the API, and every list has loading, error and empty states. |
| FR-10.6 | Forms validate locally with zod schemas mirroring backend rules, and still surface backend `400` field errors. |
