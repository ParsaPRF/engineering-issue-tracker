# Assumptions and Open Questions

Each assumption is **reversible** and documented with its blast radius: what changes if the
assumption is wrong. None of them block implementation.

## Decisions taken as assumptions (no answer needed to proceed)

| # | Assumption | Rationale | If wrong, what changes |
| --- | --- | --- | --- |
| A-1 | Interface language is **English**, single locale, no RTL in v1 (ADR-015). | Requirements are written in English; adding i18n later is additive. | Add Django locales + frontend i18n and `dir="rtl"`; layout uses logical CSS properties where cheap to allow this. |
| A-2 | Users authenticate with **email + password** (no username field). | Email is the universal identifier for a team tool. | Add a `username` field and adjust the login serializer + `USERNAME_FIELD`. |
| A-3 | Registration is **open**; new accounts get the lowest-privilege role (`REPORTER`) and no project access. | A team tool needs an onboarding path; project access is still invitation-only. | Add an allow-list/invite-only flag (`ALLOW_SELF_REGISTRATION`) — already an env-driven setting. |
| A-4 | There is exactly **one organisation** per deployment (single tenant). | Simplifies every query; project isolation covers the stated requirements. | Add an `Organization` model above `Project` and scope memberships to it. |
| A-5 | Ticket keys are `PROJECTKEY-N` with `N` starting at 1 and **gaps allowed**. | Gaps are inevitable with retries/rollbacks; contiguous numbering is not a business need. | Only matters if auditors require gapless numbering — then the counter must be allocated after commit, accepting duplicates-on-rollback risk instead. |
| A-6 | The **reporter** is always the creator; a ticket cannot be filed on behalf of another user through the API (an Admin can reassign `reporter` via the Django admin only). | Prevents spoofing; on-behalf-of filing has no stated need. | Add an `on_behalf_of` permission for PMs and an explicit audit note. |
| A-7 | Comments are **flat** (no threading/replies). | Not requested; flat threads are easier to read and to audit. | Add `parent` FK and switch the API serializer to a nested representation. |
| A-8 | A ticket belongs to exactly **one project** and cannot be moved between projects. | Moving would invalidate keys, components and memberships. | Add a "move ticket" service that re-keys the ticket and records an audit event; treat as a separate feature. |
| A-9 | Conventional commit-ish **Git history**, one branch (`main`) for this delivery. | Solo delivery; documented workflow. | Introduce feature branches + PR review if a team joins. |
| A-10 | Notifications are **in-app only** (a `Notification` row + Celery dispatch hook). No SMTP/SMS provider is configured. | No credentials available and none requested; the dispatch seam is what matters. | Implement the concrete sender (email/webhook) behind `notifications.senders`. |
| A-11 | Object storage is **MinIO** in Docker with a private bucket; local development uses the filesystem. | MinIO is S3-compatible and self-hostable. | Switch `DEFAULT_FILE_STORAGE` to S3/other provider; the authorising download view is unchanged. |
| A-12 | Attachments allow-list: images (`png/jpg/jpeg/gif/webp`), documents (`pdf/txt/csv/json/log`), archives (`zip`) and office formats; **SVG and HTML are rejected**; max 10 MB. | SVG/HTML are stored-XSS vectors when served inline; the limit keeps memory bounded. | Adjust `ATTACHMENT_ALLOWED_EXTENSIONS` / `ATTACHMENT_MAX_BYTES` via env. |
| A-13 | Local test/dev may use SQLite (`DB_ENGINE=sqlite`); PostgreSQL is the production and Docker target. | The current machine has no PostgreSQL and no running Docker daemon. | Nothing in the code changes; only the engine and the Postgres-marked tests that get skipped. |
| A-14 | "Engineer" (project role) is the only project role that can be an assignee, together with project managers. | Reflects who does the work. | Extend `ELIGIBLE_ASSIGNEE_ROLES` in `projects/permissions.py`. |
| A-15 | API pagination default is 25 items, max 100; ordering defaults to `-created_at`. | Sane defaults for dashboards. | Client passes `page_size`; change defaults in `common/pagination.py`. |
| A-16 | The audit table is append-only by convention plus production DB privileges (revoke `UPDATE`/`DELETE`). | True immutability at DB level needs role separation, which is documented but cannot be verified without a running PostgreSQL. | Deployment guide step; verify in the Docker environment once available. |

## Open questions (answers would improve the product, none block the MVP)

| # | Question | Impact if answered differently | Default until answered |
| --- | --- | --- | --- |
| Q-1 | Should registration be restricted to invited users, or is open registration intended for an internal network? | Changes `A-3`: one setting plus a UI hint. | Open registration, lowest role. |
| Q-2 | Are **SLA / due-date reminders** expected (e.g. notify 24 h before `due_date`)? | Adds a periodic Celery task and a notification type. | Not implemented; `due_date` is stored and "overdue" is filterable. |
| Q-3 | Should closing a `RESOLVED` ticket require the **reporter's** confirmation? | Adds a confirmation workflow and a `PENDING_CONFIRMATION`-style state. | PM/Admin close directly. |
| Q-4 | Is there a need for **cross-project reporting** roles (a user who sees all projects without being a member)? | Adds a global "read all" flag checked in the permission kernel. | Only Admin sees everything. |
| Q-5 | Should ticket **watchers/subscribers** exist (a user follows a ticket without being the reporter or assignee)? | Adds `TicketWatcher` and expands every notification recipient computation. | Reporter + assignee + managers are notified. |
| Q-6 | Do you want **email delivery**, and if so which provider and from-address? | Implements `notifications.senders.EmailSender` + SMTP env vars. | In-app only (A-10). |
| Q-7 | Are **time tracking** and sprint boards in scope for v2? | Significant new models (`TimeEntry`, `Sprint`). | Out of scope (see system-overview non-goals). |
| Q-8 | Should the **frontend be served by Nginx as static files** in the same container as the API, or as a separate service? | Deployment topology only; both are documented. | Separate `frontend` build artefact served by Nginx (already the compose design). |
| Q-9 | Confirm the UI language choice (`A-1`) — English now, Persian/RTL later? | Localisation work in both backend and frontend. | English now; RTL-friendly CSS conventions. |
| Q-10 | Is an **Admin UI in Django admin** acceptable as the "Team Management" surface for role changes, or does it need a bespoke React screen? | One extra React screen with role-change controls. | Both: Django admin is enabled, and the React Team screen covers membership management; system-role changes are React-side for Admins. |

## Environment constraints observed during implementation (honest reporting)

| Observation | Consequence |
| --- | --- |
| No PostgreSQL server installed locally; Docker daemon not running, Docker Desktop not installed (the `docker` CLI exists but `docker info` fails on `npipe:////./pipe/dockerDesktopLinuxEngine`). | Docker Compose files and health checks are authored and syntax-checked, but **`docker compose up` could not be executed or verified in this environment**. PostgreSQL-specific behaviour is covered by `postgres`-marked tests that were **skipped** locally. This is stated again in the deployment guide and final report. |
| No Redis server locally. | Celery runs in eager mode for tests; the broker path is configured but not exercised against a live Redis here. |
| Git repository root is `C:\Users\parsa` (the user's home directory, an unrelated repository). | The project is created as its **own** git repository inside `eng-tracker/` so that unrelated files are never staged. |
