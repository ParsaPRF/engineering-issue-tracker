# Use Cases

Actors: **Visitor**, **Reporter**, **Engineer**, **Project Manager (PM)**, **Admin**.
"Member" means an active `ProjectMembership` in the affected project.

---

## UC-01 Register

* **Actor:** Visitor. **Goal:** obtain an account.
* **Preconditions:** none.
* **Main flow:** POST email/full name/password → password validators run → user created with
  `system_role = REPORTER` → audit event `user.registered` → 201 with the created profile.
* **Alternative:** email already used → `400` with a field error; weak password → `400` listing
  the failed validator messages.
* **Postcondition:** the user can log in but sees no projects until added to one.

## UC-02 Log in

* **Actor:** any user. **Goal:** obtain an authenticated session.
* **Main flow:** POST email/password → credentials verified → session created → `Set-Cookie`
  (`HttpOnly`) → 200 with the user payload.
* **Alternative:** wrong credentials → `400/401` with a generic message (no user enumeration);
  inactive account → `403 account_inactive`.
* **Postcondition:** subsequent requests authenticate via the session cookie.

## UC-03 Create a project

* **Actor:** Admin or PM. **Goal:** open a container for work.
* **Main flow:** POST key/name/description → key normalised to uppercase and checked unique →
  project created with `owner = actor` → actor added as active `MANAGER` membership → audit event
  → 201.
* **Alternative:** duplicate key → `400`; `REPORTER` or `ENGINEER` actor → `403`.
* **Postcondition:** the project appears in the actor's project list.

## UC-04 Add a project member

* **Actor:** PM or Admin. **Goal:** give a user access to the project.
* **Main flow:** POST user id + project role → target user must be active → membership created or
  reactivated → audit event `membership.added` → notification to the target.
* **Alternative:** target not an active user → `400`; actor cannot manage members → `403`.
* **Postcondition:** the target can now see the project according to their project role.

## UC-05 Report a ticket

* **Actor:** any member. **Goal:** record an issue.
* **Main flow:** POST title/description/type/priority/severity (+ optional component, assignee,
  due date) → permission check → key allocated atomically (`ENG-1042`) → ticket created in `NEW`
  → initial `TicketStatusHistory` row (`from_status = null`) → audit event → notification to
  project managers → 201.
* **Alternative:** non-member → `404` (project not visible); invalid component from another
  project → `400`; archived project → `400 project_archived`.
* **Postcondition:** the ticket is visible to project members; the reporter is the actor.

## UC-06 Triage a ticket

* **Actor:** PM/Admin. **Goal:** accept or dismiss new work.
* **Main flow:** `NEW → TRIAGED` (optionally with a component/priority/severity fix-up and an
  assignee), or `NEW → REJECTED`/`DUPLICATE` with a mandatory reason comment.
* **Alternative:** illegal target → `400 invalid_transition`; missing comment → `400`.
* **Postcondition:** history and audit rows record the decision.

## UC-07 Assign or reassign a ticket

* **Actor:** PM/Admin (any eligible member); Engineer (self-assign, unassigned only).
* **Main flow:** POST assignee id → assignee must be an active member whose project role is
  ENGINEER or MANAGER → ticket updated → audit event → notification to the new assignee
  (`ticket.assigned` or `ticket.reassigned` depending on the previous value).
* **Alternative:** assignee is a `REPORTER`-only member → `400 ineligible_assignee`;
  engineer assigning someone else → `403`.
* **Postcondition:** the ticket shows in the assignee's "My assignments".

## UC-08 Move a ticket through its lifecycle

* **Actor:** depends on the move (see `docs/architecture/workflow.md`).
* **Main flow:** the UI loads allowed transitions → user picks one (and supplies a comment when
  required) → service validates state, permission, guards → status updated atomically with
  history and audit → notification queued.
* **Alternative:** stale UI (someone else already moved it) → `400 invalid_transition` with the
  current status in the error detail, so the client can refresh.
* **Postcondition:** `resolved_at`/`closed_at` stamped or cleared as appropriate.

## UC-09 Comment on a ticket

* **Actor:** any member. **Main flow:** POST body → ticket visible → comment created → audit event
  → notification to reporter, assignee and managers except the author.
* **Alternative:** empty/oversized body → `400`.
* **Postcondition:** the comment appears in the ticket timeline.

## UC-10 Edit or delete a comment

* **Actor:** the comment's author; or PM/Admin for moderation.
* **Main flow:** PATCH body (author, within the edit window) → `edited_at` set; DELETE → soft
  delete flagged, body retained for audit but hidden from the UI.
* **Alternative:** outside window or not the author → `403`; already deleted → `404`.

## UC-11 Attach evidence

* **Actor:** any member. **Main flow:** multipart POST with `ticket` or `comment` → extension,
  content type and size validated → object stored under a random key → metadata row with SHA-256
  → audit event → 201 with metadata only (no URL).
* **Alternative:** oversized → `400 attachment_too_large`; disallowed type → `400
  unsupported_file_type`; no stored object is left behind on failure.
* **Postcondition:** the attachment can be downloaded only through the authorised endpoint.

## UC-12 Download an attachment

* **Actor:** member of the owning project. **Main flow:** GET `/attachments/<id>/download/` →
  permission re-checked from the attachment to its ticket's project → streamed with
  `Content-Disposition` and the original filename → access recorded in the audit trail.
* **Alternative:** non-member or deleted attachment → `404`.

## UC-13 Review team workload

* **Actor:** PM/Admin. **Goal:** see who is loaded.
* **Main flow:** open Reports → workload per engineer for visible projects (open ticket counts by
  status) → drill into a filtered ticket list.

## UC-14 Monitor the project

* **Actor:** any member. **Main flow:** open Dashboard → totals, open/resolved/blocked, breakdown
  by priority/severity/type/project, recent activity. Non-members' projects are excluded from
  every number.

## UC-15 Receive and read notifications

* **Actor:** any user. **Main flow:** trigger something (UC-07/08/09) → a notification row is
  created for each recipient and queued → the bell shows the unread count → the user opens the
  list and marks items read, individually or all at once.
* **Alternative:** the Celery worker is down → rows stay `is_sent = False` and are re-queued by
  the periodic retry task; the user still sees them in-app.

## UC-16 Audit a change

* **Actor:** Admin. **Main flow:** open Audit → filter by actor, action, project, object or date
  range → inspect metadata. No endpoint can modify or delete events.

## UC-17 Deactivate a user

* **Actor:** Admin. **Main flow:** set `is_active = False` → all sessions invalidated → the user
  can no longer authenticate → their tickets, comments and audit history remain intact and
  attributable → audit event `user.deactivated`.
* **Alternative:** attempting to delete a user who owns a project or reported tickets → `409`
  with an explanation, because of `PROTECT` foreign keys.
