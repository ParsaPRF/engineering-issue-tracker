# Test Scenarios

Every scenario below states what is being proven, how to reproduce it, and **which automated test
covers it** — so a reviewer can jump from a claim to the code that defends it. Nothing in the
"Automated coverage" column was invented: each name is a real test that runs in CI.

Run everything with:

```bash
cd backend
.venv/Scripts/python -m pytest -q            # 237 passed, 1 skipped (PostgreSQL-only)
DB_ENGINE=postgres pytest -q                 # 238 passed, 0 skipped (needs PostgreSQL)
```

**Status legend**

| Mark | Meaning |
| --- | --- |
| ✅ auto | Covered by an automated test that runs on every push |
| 🐘 auto (pg) | Covered by an automated test that needs PostgreSQL (CI runs it, a local SQLite run skips it) |
| 🖐 manual | Verified by hand in the UI/API; the steps are written out below |
| ⛔ gap | Not covered — listed in §10 with the reason |

---

## 1. Authentication and identity

| ID | Req | Scenario | Precondition | Steps | Expected result | Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| S-A-01 | FR-1.1 | Register a new account | No account with that email | `POST /api/v1/auth/register/` with email, name, password, confirmation | `201`; account exists with role `REPORTER`; profile created; audit `user.registered` | ✅ `test_auth.py::test_register_creates_reporter_with_profile_and_audit_event` |
| S-A-02 | FR-1.1 | Email already taken (different case) | `Taken@Example.com` exists | Register with `TAKEN@example.com` | `400 email_taken`; only one row in the database | ✅ `test_register_rejects_duplicate_email_case_insensitively` |
| S-A-03 | FR-1.8 | Weak password | — | Register with `password`/`password` | `400 validation_error`; account not created | ✅ `test_register_rejects_weak_password` |
| S-A-04 | FR-1.8 | Confirmation mismatch | — | Register with two different passwords | `400`; field error on `password_confirm` | ✅ `test_register_rejects_mismatched_confirmation` |
| S-A-05 | A-3 | Self-registration disabled | `ALLOW_SELF_REGISTRATION=False` | Register | `403 registration_disabled` | ✅ `test_registration_can_be_disabled_by_configuration` |
| S-A-06 | FR-1.2 | Successful login | Active account | `POST /auth/login/` | `200` + user payload; `sessionid` cookie is `HttpOnly`; audit `user.logged_in` | ✅ `test_login_creates_session_and_returns_current_user` |
| S-A-07 | FR-1.2 | Wrong password | Active account | Login with a wrong password | `400 invalid_credentials` (no hint about the account) | ✅ `test_login_with_wrong_password_is_generic` |
| S-A-08 | NFR-1.3 | Unknown email is indistinguishable | — | Login with an unknown email | `400 invalid_credentials` — identical to S-A-07 | ✅ `test_login_for_unknown_email_is_indistinguishable_from_wrong_password` |
| S-A-09 | FR-1.7 | Deactivated account | `is_active=False`, correct password | Login | `403 account_inactive` (safe: the password was proven); with a wrong password → `400` | ✅ `test_inactive_account_is_reported_only_when_the_password_is_correct` |
| S-A-10 | NFR-1.4 | CSRF required on login | CSRF-enforcing client | `POST /auth/login/` without `X-CSRFToken`, then with it | `403`, then `200` | ✅ `test_login_requires_a_csrf_token_when_csrf_is_enforced` |
| S-A-11 | FR-1.3 | Logout ends the session | Logged in | `POST /auth/logout/`, then `GET /auth/me/` | `204`, then `403`; audit `user.logged_out` | ✅ `test_logout_ends_the_session` |
| S-A-12 | FR-1.7 | Deactivation kills a live session | Logged in | Admin deactivates the account → reuse the same client | `403` on the next request | ✅ `test_deactivated_user_with_a_live_session_is_rejected` |
| S-A-13 | FR-1.4 | Current user | Logged in | `GET /auth/me/` | Own profile + project memberships with roles | ✅ `test_login_creates_session_and_returns_current_user` |
| S-A-14 | FR-1.5 | Update own profile | Logged in | `PATCH /auth/me/` with name + profile fields | `200`; values persisted; invalid time zone → `400` | ✅ `test_me_patch_updates_name_and_profile`, `test_me_patch_rejects_unknown_timezone` |
| S-A-15 | NFR-1.1 | Privilege escalation through the profile form | `REPORTER` logged in | `PATCH /auth/me/` with `system_role: ADMIN` | `200` but the role is **unchanged** (field not accepted) | ✅ `test_me_patch_cannot_escalate_privileges` |
| S-A-16 | FR-1.5 | Password change | Logged in | `POST /auth/me/password/` with current + new password | `204`; other sessions invalidated, current one survives; wrong current password → `400` | ✅ `test_password_change_replaces_the_credential_and_kills_other_sessions`, `test_password_change_requires_the_current_password` |
| S-A-17 | FR-1.6 | Directory is manager-only | `ENGINEER` / `REPORTER` logged in | `GET /auth/users/directory/` | `403 permission_denied`; manager/admin → `200` with public fields only | ✅ `test_directory.py::test_non_managers_cannot_browse_the_directory`, `test_directory_returns_only_public_fields` |
| S-A-18 | NFR-1.2 | Session cookie is not readable from JS | — | Inspect cookie flags | `SESSION_COOKIE_HTTPONLY=True`, `CSRF_COOKIE_HTTPONLY=False` | ✅ `test_session_cookie_is_not_readable_from_javascript` |
| S-A-19 | FR-1.5 | Log in from the browser | Stack running | Open `/login`, submit demo credentials | Redirect to the intended page; the bell shows the unread count | 🖐 manual |

## 2. Projects and membership

| ID | Req | Scenario | Precondition | Steps | Expected result | Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| S-P-01 | FR-2.1 | Create a project | Manager | `POST /projects/` with key `eng`, name | `201`; key stored as `ENG`; creator is owner **and** an active manager | ✅ `test_projects.py::test_manager_can_create_project_and_becomes_its_manager` |
| S-P-02 | FR-2.1 | Non-managers cannot create projects | `ENGINEER`/`REPORTER` | `POST /projects/` | `403`; nothing created | ✅ `test_engineer_and_reporter_cannot_create_projects` |
| S-P-03 | FR-2.2 | Duplicate key, different case | `DUP` exists | Create with key `dup` | `400 duplicate_project_key`; still one project | ✅ `test_duplicate_project_key_is_rejected_case_insensitively` |
| S-P-04 | FR-2.2 | Malformed key | Manager | Create with key `has space` | `400` with a field error on `key` | ✅ `test_invalid_project_key_is_rejected` |
| S-P-05 | FR-2.7 | List is scoped to membership | Member of one project | `GET /projects/` | Only that project; an admin sees all | ✅ `test_project_list_only_contains_the_callers_projects`, `test_admin_sees_every_project` |
| S-P-06 | NFR-1.3 | Foreign project is invisible (not forbidden) | Stranger | `GET /projects/{id}/` | `404 not_found` — existence is not confirmed | ✅ `test_foreign_project_detail_returns_404_not_403` |
| S-P-07 | FR-2.3 | Update a project | Manager | `PATCH /projects/{id}/` name + description | `200`; audit `project.updated` records from→to | ✅ `test_manager_can_update_project_fields` |
| S-P-08 | FR-2.3 | The key is immutable | Manager | `PATCH` with a different `key` | `200` but `key` unchanged (it prefixes every ticket key) | ✅ `test_project_key_cannot_be_changed` |
| S-P-09 | FR-2.3 | Member without the manager role | Engineer member | `PATCH /projects/{id}/` | `403 permission_denied` (visible project, insufficient role) | ✅ `test_member_without_manager_role_cannot_update_project` |
| S-P-10 | FR-2.4 | Archive and restore | Manager | `POST /projects/{id}/archive/`, again, then `/restore/` | `200`; second archive → `400 already_archived`; restore clears `archived_at` | ✅ `test_archive_and_restore_project` |
| S-P-11 | FR-2.4 | No delete endpoint | Manager | `DELETE /projects/{id}/` | `405`; the project still exists | ✅ `test_project_has_no_delete_endpoint` |
| S-P-12 | FR-2.5 | Add a member with a project role | Manager | `POST /projects/{id}/members/` | `201`; membership active; audit `membership.added` | ✅ `test_memberships.py::test_manager_can_add_member_with_a_project_role` |
| S-P-13 | FR-2.5 | Non-manager cannot add members | Engineer member | Add a member | `403`; nothing created | ✅ `test_non_manager_cannot_add_members` |
| S-P-14 | FR-2.5 | Add a deactivated user | `is_active=False` | Add as member | `400 inactive_user` | ✅ `test_deactivated_user_cannot_be_added` |
| S-P-15 | FR-2.5 | Re-adding a removed member | Membership inactive | Add again with a new role | `200`; **the same row is reactivated** (no duplicate) | ✅ `test_re_adding_a_removed_member_reactivates_the_row` |
| S-P-16 | FR-2.5 | Demote the last manager | One manager | `PATCH .../members/{id}/` role→ENGINEER | `400` (`last_manager` or `owner_must_be_manager`) | ✅ `test_the_last_manager_cannot_be_demoted` |
| S-P-17 | FR-2.5 | Remove the owner | Manager | `DELETE .../members/{owner}/` | `400 owner_cannot_be_removed` | ✅ `test_owner_cannot_be_removed` |
| S-P-18 | FR-4.3 | Removing a member clears their open assignments | Engineer with an open ticket | Remove the membership | `204`; the ticket becomes unassigned (access and workload stay consistent) | ✅ `test_removing_a_member_clears_their_open_assignments` |
| S-P-19 | NFR-1.3 | Membership IDOR across projects | Manager of A, membership of B | `PATCH /projects/A/members/{B's id}/` | `404` | ✅ `test_membership_from_another_project_is_not_reachable` |
| S-P-20 | FR-2.6 | Create a component | Manager | `POST /projects/{id}/components/` | `201`; audit `component.created` | ✅ `test_manager_can_create_component` |
| S-P-21 | FR-2.6 | Component name unique per project | `Mobile App` exists | Create `mobile app` | `400 duplicate_component_name` | ✅ `test_component_name_is_unique_inside_a_project` |
| S-P-22 | FR-2.6 | Lead must be a member | Outsider | Create with `lead=<outsider>` | `400 ineligible_lead` | ✅ `test_component_lead_must_be_a_project_member` |
| S-P-23 | FR-2.6 | Deactivate a component without losing tickets | Component on tickets | `POST /components/{id}/deactivate/` | `200`; tickets keep the reference; audit recorded | ✅ `test_component_can_be_deactivated_without_losing_tickets` |
| S-P-24 | FR-2.8 | Project statistics | Project with tickets | `GET /projects/{id}/stats/` | Counts + breakdowns; foreign project → `404` | ✅ `test_project_stats_endpoint_is_permission_scoped` |

## 3. Tickets

| ID | Req | Scenario | Precondition | Steps | Expected result | Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| S-T-01 | FR-3.1 | Create a ticket | Project member | `POST /tickets/` | `201`; key `PROJECTKEY-N`; status `NEW`; reporter = caller; timeline opened; audit `ticket.created` | ✅ `test_tickets.py::test_member_can_create_ticket_with_generated_key_and_new_status`, `test_ticket_creation_opens_the_timeline_and_the_audit_trail` |
| S-T-02 | FR-3.2 | Keys are sequential per project | — | Allocate 1, 2, 3 | `ENG-1`, `ENG-2`, `ENG-3`; other projects start at 1 | ✅ `test_ticket_keys.py::test_first_key_of_a_project_is_number_one`, `test_keys_are_sequential_per_project`, `test_counters_are_independent_between_projects` |
| S-T-03 | FR-3.3 | Drifted counter | Key `ENG-1` exists, counter reset to 0 | Allocate | Returns `ENG-2` (never a duplicate) | ✅ `test_allocator_skips_a_key_that_already_exists` |
| S-T-04 | FR-3.3 | Lost race for a key | Another committed row holds the next key | Create a ticket | The service retries once and succeeds; the other row is untouched | ✅ `test_retry_path_recovers_when_another_writer_took_the_key` |
| S-T-05 | FR-3.3 | **Concurrent creation** | PostgreSQL | 8 threads create tickets at the same instant | 8 distinct keys, 8 rows, no `IntegrityError` | 🐘 `test_concurrent_creation_never_duplicates_a_key` |
| S-T-06 | FR-3.5 | Status cannot be set on create | — | `POST /tickets/` with `status: CLOSED` | `201` but the ticket is `NEW` (unknown fields are not honoured) | ✅ `test_client_cannot_forge_status_on_creation` |
| S-T-07 | FR-3.4 | Reporter cannot be forged | — | `POST /tickets/` with someone else's id as `reporter` | `201`; reporter is the caller | ✅ `test_client_cannot_forge_reporter` |
| S-T-08 | FR-3.5 | Status cannot be patched | Existing ticket | `PATCH /tickets/{id}/` with `status` | `400 use_transition_endpoint`; status unchanged | ✅ `test_patch_status_is_rejected_with_a_helpful_error` |
| S-T-09 | FR-4.1 | Assignee cannot be patched | Existing ticket | `PATCH` with `assignee` | `400 use_assignment_endpoint` | ✅ `test_patch_assignee_is_rejected_in_favour_of_the_assign_endpoint` |
| S-T-10 | FR-3.2 | Key and project immutable | Existing ticket | `PATCH` with `key`/`project` | `200`; both unchanged | ✅ `test_key_and_project_are_immutable` |
| S-T-11 | FR-3.9 | Reporter edits their own ticket | Reporter, ticket open | `PATCH` title/priority | `200`; audit records from→to | ✅ `test_reporter_can_edit_their_own_ticket` |
| S-T-12 | FR-3.9 | Reporter edits a closed ticket | Status `CLOSED` | `PATCH` title | `403` | ✅ `test_reporter_cannot_edit_a_closed_ticket` |
| S-T-13 | FR-3.9 | Reporter edits someone else's ticket | Another reporter's ticket | `PATCH` title | `403 field_not_editable` / `permission_denied` | ✅ `test_reporter_cannot_edit_someone_elses_ticket` |
| S-T-14 | FR-3.9 | Assignee edits working fields | Assignee | `PATCH` component + severity | `200` | ✅ `test_assignee_can_edit_working_fields` |
| S-T-15 | FR-3.6 | Component from another project | Foreign component | `POST /tickets/` with it | `404` (not resolvable inside this project) | ✅ `test_component_from_another_project_is_rejected` |
| S-T-16 | FR-4.1 | Reporter-role member as assignee | Member with project role `REPORTER` | Create/assign with them as assignee | `400 ineligible_assignee` | ✅ `test_reporter_role_member_cannot_be_the_assignee` |
| S-T-17 | FR-2.4 | Archived project rejects tickets | Project archived | `POST /tickets/` | `400 project_archived` | ✅ `test_archived_project_rejects_new_tickets` |
| S-T-18 | NFR-1.3 | Outsider creates a ticket | Not a member | `POST /tickets/` | `404`; nothing created | ✅ `test_outsider_cannot_create_ticket` |
| S-T-19 | FR-3.8 | Foreign tickets never appear in lists | Outsider | `GET /tickets/`, `GET /tickets/{id}/` | Empty list; detail `404` | ✅ `test_ticket_list_never_contains_foreign_projects`, `test_foreign_ticket_detail_is_404` |
| S-T-20 | FR-3.7 | Multi-value status filter | Tickets in 3 states | `?status=NEW,IN_PROGRESS` | Only those two kinds | ✅ `test_filter_by_multiple_statuses` |
| S-T-21 | FR-3.7 | Assignee / unassigned filters | Mixed assignments | `?assignee=<id>`, `?unassigned=true` | One row each | ✅ `test_filter_by_assignee_and_unassigned` |
| S-T-22 | FR-3.7 | Overdue filter | One past due, one future | `?overdue=true` | Only the overdue one, with `is_overdue: true` | ✅ `test_filter_overdue` |
| S-T-23 | FR-3.7 | Search by key and title | — | `?search=<key>` / `?search=gateway` | Exact matching rows | ✅ `test_search_matches_key_and_title` |
| S-T-24 | FR-3.7 | Priority ordering is semantic | LOW, CRITICAL, MEDIUM | `?ordering=-priority` then `?ordering=priority` | CRITICAL→MEDIUM→LOW, then the reverse (**not** alphabetical) | ✅ `test_ordering_by_priority_is_semantic_not_alphabetical` |
| S-T-25 | NFR-2.3 | Pagination cap | — | `?page_size=5000` | `page_size` capped at 100 | ✅ `test_project_list_is_paginated_with_a_capped_page_size`, `test_ticket_list_is_paginated` |
| S-T-26 | FR-4.4 | My assignments | Tickets assigned to me | `GET /tickets/my-assignments/` | Only my **open** tickets; `?include_done=true` adds finished work | ✅ `test_my_assignments_returns_only_my_open_tickets`, `test_my_assignments_can_include_finished_work` |
| S-T-27 | FR-3.7 | Form metadata | Logged in | `GET /tickets/choices/` | Statuses/types/priorities/severities from the backend | ✅ `test_choices_endpoint_exposes_enumerations` |
| S-T-28 | FR-10.2 | Create a ticket in the UI | Stack running | Tickets → New ticket → fill → submit | Redirect to the ticket; it appears in the list with its key | 🖐 manual |

## 4. Workflow (state machine)

| ID | Req | Scenario | Precondition | Steps | Expected result | Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| S-W-01 | FR-5.2 | Full lifecycle | Ticket with assignee | TRIAGED → IN_PROGRESS → IN_REVIEW → RESOLVED → CLOSED | Each step `200`; final status `CLOSED`; `resolved_at`/`closed_at` stamped; timeline has 6 entries | ✅ `test_workflow.py::test_full_lifecycle_from_new_to_closed` |
| S-W-02 | FR-5.2 | **Every declared move × every project role** | — | For each of the 19 rules and 3 roles | Allowed roles succeed and roll back correctly; others get `403` and the status is unchanged | ✅ `test_workflow_matrix.py::test_each_declared_move_respects_the_role_matrix` (19 parametrised cases) |
| S-W-03 | FR-5.2 | **Every undeclared move** | — | All 71 remaining (from,to) pairs | `400 invalid_transition`; status unchanged | ✅ `test_every_undeclared_move_is_refused` |
| S-W-04 | FR-5.1 | No-op move | Ticket in `TRIAGED` | `TRIAGED → TRIAGED` | `400 noop_transition` | ✅ `test_noop_transition_is_rejected` |
| S-W-05 | FR-5.2 | Impossible jump | Ticket in `NEW` | `NEW → RESOLVED` | `400 invalid_transition`; no history row | ✅ `test_invalid_jump_is_rejected` |
| S-W-06 | FR-5.2 | Unknown status | — | `to_status: TELEPORTED` | `400 invalid_status` | ✅ `test_unknown_status_is_rejected` |
| S-W-07 | FR-5.3 | Comment required | Ticket in `NEW` | `NEW → REJECTED` without a comment, then with `"   "`, then with a real one | `400 comment_required`, `400`, `200` | ✅ `test_rejection_requires_a_comment` |
| S-W-08 | FR-5.4 | Assignee required | `TRIAGED`, no assignee | `TRIAGED → IN_PROGRESS` | `400 assignee_required`; status unchanged | ✅ `test_starting_work_requires_an_assignee` |
| S-W-09 | FR-5.3 | Blocking needs a reason | `IN_PROGRESS` | `IN_PROGRESS → BLOCKED` without a comment | `400 comment_required` | ✅ `test_blocking_requires_a_reason` |
| S-W-10 | FR-5.5 | History + audit written together | — | Any accepted transition | One history row (from,to,actor,comment) **and** one audit event referencing it | ✅ `test_transition_records_history_and_audit_together` |
| S-W-11 | FR-5.6 | Reopen clears stamps | `CLOSED` with timestamps | `CLOSED → REOPENED` with a comment | `resolved_at`/`closed_at` become `null` | ✅ `test_reopen_clears_resolution_timestamps` |
| S-W-12 | FR-5.7 | Reporter cannot triage | Reporter | `NEW → TRIAGED` | `403 transition_not_permitted` | ✅ `test_reporter_cannot_triage` |
| S-W-13 | FR-5.7 | Engineer cannot close | Engineer | `RESOLVED → CLOSED` | `403` | ✅ `test_engineer_cannot_close` |
| S-W-14 | FR-5.7 | Outsider cannot transition | Not a member | Any transition | `404` | ✅ `test_outsider_cannot_transition_a_foreign_ticket` |
| S-W-15 | FR-5.7 | Assignee moves their own ticket | Assignee, `TRIAGED` | `TRIAGED → IN_PROGRESS` | `200` | ✅ `test_assignee_can_move_their_own_ticket_forward` |
| S-W-16 | FR-5.7 | Admin bypasses project roles | System `ADMIN` | `RESOLVED → CLOSED` | `200` | ✅ `test_admin_bypasses_project_roles` |
| S-W-17 | FR-5.8 | Allowed moves match permissions | `RESOLVED` ticket | `GET /workflows/transitions/?ticket=…` as manager and as engineer | Manager: `CLOSED`+`REOPENED`; engineer: only `REOPENED` | ✅ `test_allowed_transitions_endpoint_matches_permissions` |
| S-W-18 | FR-5.8 | Blocking preconditions are explained | `TRIAGED`, no assignee | Same endpoint | The `IN_PROGRESS` move is present with `available: false`, `blocked_by: ["assignee_required"]` | ✅ `test_allowed_transitions_reports_blocking_preconditions` |
| S-W-19 | FR-5.8 | History endpoint | After 2 transitions | `GET /tickets/{id}/history/` | `NEW → TRIAGED` timeline with actor names; first row has `from_status: null` | ✅ `test_history_endpoint_returns_the_timeline` |
| S-W-20 | FR-5.8 | Catalogue | — | `GET /workflows/` | 10 statuses, 19 moves | ✅ `test_workflow_catalogue_is_available` |
| S-W-21 | ADR-005 | The table itself is coherent | — | Inspect the table | No duplicate (from,to) pair; every rule allows at least one role | ✅ `test_table_has_no_duplicate_pairs`, `test_every_rule_allows_a_manager_somewhere` |
| S-W-22 | FR-10.5 | UI transition buttons come from the API | Stack running | Open a ticket as manager, then as engineer | The offered buttons differ per role; a blocked move shows its reason | 🖐 manual |

## 5. Assignment

| ID | Req | Scenario | Steps | Expected result | Coverage |
| --- | --- | --- | --- | --- | --- |
| S-AS-01 | FR-4.1 | Manager assigns an unassigned ticket | `POST /tickets/{id}/assign/` | `200`; audit `ticket.assigned`; notification for the assignee | ✅ `test_assignment.py::test_manager_can_assign_an_unassigned_ticket` |
| S-AS-02 | FR-4.2 | Reassignment | Assign from A to B | `200`; audit `ticket.reassigned` with from/to | ✅ `test_reassignment_is_recorded_as_such` |
| S-AS-03 | FR-4.1 | Unassign | `assignee: null` as manager | `200`; audit `ticket.unassigned` | ✅ `test_manager_can_unassign` |
| S-AS-04 | FR-4.1 | Unassign an unassigned ticket | `assignee: null` | `200`; **no** audit event (nothing happened) | ✅ `test_unassigning_an_unassigned_ticket_is_a_noop` |
| S-AS-05 | FR-4.2 | Engineer self-assigns a free ticket | `assignee: <self>` | `200` | ✅ `test_engineer_can_self_assign_an_unassigned_ticket` |
| S-AS-06 | FR-4.2 | Engineer tries to take an assigned ticket | `assignee: <self>` | `403`; assignee unchanged | ✅ `test_engineer_cannot_steal_an_assigned_ticket` |
| S-AS-07 | FR-4.2 | Engineer assigns somebody else | `assignee: <other>` | `403` | ✅ `test_engineer_cannot_assign_another_person` |
| S-AS-08 | FR-4.2 | Engineer unassigns somebody else | `assignee: null` | `403` | ✅ `test_engineer_cannot_unassign_somebody_else` |
| S-AS-09 | FR-4.1 | Ineligible / non-member / deactivated assignee | Assign to a REPORTER, an outsider, then a deactivated engineer | `400 ineligible_assignee` in all three cases | ✅ `test_reporter_role_member_is_not_eligible`, `test_non_member_cannot_be_assigned`, `test_deactivated_engineer_cannot_be_assigned` |
| S-AS-10 | FR-4.1 | Assignment does not change status | `TRIAGED` ticket assigned | Status stays `TRIAGED` | ✅ `test_assignment_does_not_change_status` |
| S-AS-11 | NFR-1.3 | Outsider cannot assign | `POST .../assign/` | `404` | ✅ `test_outsider_cannot_assign_anything` |

## 6. Comments and attachments

| ID | Req | Scenario | Steps | Expected result | Coverage |
| --- | --- | --- | --- | --- | --- |
| S-C-01 | FR-6.1 | Comment on a ticket | `POST /tickets/{id}/comments/` | `201`; audit; notification for the audience | ✅ `test_comments.py::test_member_can_comment` |
| S-C-02 | FR-6.1 | Empty comment | body `"   "` | `400 validation_error` | ✅ `test_empty_comment_is_rejected` |
| S-C-03 | FR-6.1 | Oversized comment | 10 001 characters | `400` | ✅ `test_comment_length_is_bounded` |
| S-C-04 | NFR-1.3 | Outsider comments | — | `404` | ✅ `test_outsider_cannot_comment` |
| S-C-05 | FR-6.2 | Author edits within the window | `PATCH /comments/{id}/` | `200`; `edited_at` set; audit `comment.updated` | ✅ `test_author_can_edit_within_the_window` |
| S-C-06 | FR-6.2 | Edit window closed | Comment 2 h old | `400 edit_window_closed` | ✅ `test_edit_window_closes` |
| S-C-07 | FR-6.2 | Manager rewrites someone's comment | `PATCH` as manager | `403`; body unchanged (managers moderate, they do not edit) | ✅ `test_only_the_author_can_edit` |
| S-C-08 | FR-6.3 | Author deletes (soft) | `DELETE /comments/{id}/` | `204`; row kept with `is_deleted`; audit | ✅ `test_author_can_delete_their_comment_softly` |
| S-C-09 | FR-6.3 | Manager moderates | `DELETE` as manager | `204`; audit records `as_moderator: true` | ✅ `test_manager_can_moderate_any_comment` |
| S-C-10 | FR-6.5 | Upload a valid file | `POST /tickets/{id}/attachments/` (multipart) | `201`; random storage key; sha256; audit | ✅ `test_attachments.py::test_member_can_upload_a_ticket_attachment` |
| S-C-11 | NFR-1.8 | Path traversal in the filename | Upload as `../../etc/passwd.txt` | Stored under `attachments/<uuid>.txt`; no path components survive | ✅ `test_storage_key_is_random_and_keeps_only_the_extension` |
| S-C-12 | NFR-1.8 | Dangerous type | Upload `payload.svg` | `400 dangerous_file_type`; nothing stored | ✅ `test_executable_extension_is_rejected` |
| S-C-13 | NFR-1.8 | Type outside the allow-list | Upload `data.bin` | `400 unsupported_file_type` | ✅ `test_extension_outside_the_allow_list_is_rejected` |
| S-C-14 | NFR-1.8 | Oversized file | `ATTACHMENT_MAX_BYTES=10` | `400 attachment_too_large` with a readable message | ✅ `test_oversized_file_is_rejected_with_an_actionable_message` |
| S-C-15 | FR-6.7 | No public storage URL | Upload response | Only `download_url` (an API path); no bucket URL | ✅ `test_serializer_never_exposes_a_storage_url` |
| S-C-16 | FR-6.7 | Authorised download | `GET /attachments/{id}/download/` | `200`, `application/octet-stream`, `Content-Disposition: attachment`, bytes identical | ✅ `test_authorised_member_can_download` |
| S-C-17 | NFR-1.3 | Outsider downloads | — | `404` | ✅ `test_outsider_gets_404_for_a_download` |
| S-C-18 | FR-6.8 | Deleted attachment is unreachable | Upload, delete, download | `404` | ✅ `test_deleted_attachment_is_not_downloadable` |
| S-C-19 | FR-6.8 | Uploader deletes | `DELETE /attachments/{id}/` | `204`; row flagged; object removed after commit; audit | ✅ `test_uploader_can_delete_and_the_object_is_removed` |
| S-C-20 | FR-6.6 | Attachment on a comment | `POST /comments/{id}/attachments/` | `201`; effective ticket resolved through the comment | ✅ `test_attachment_on_comment_belongs_to_the_comment_ticket` |

## 7. Notifications and audit

| ID | Req | Scenario | Steps | Expected result | Coverage |
| --- | --- | --- | --- | --- | --- |
| S-N-01 | FR-7.1 | Ticket creation notifies managers | Reporter creates a ticket | Managers get a row; the reporter (actor) does not | ✅ `test_notifications.py::test_ticket_creation_notifies_project_managers` |
| S-N-02 | FR-7.1 | Assignment notifies the assignee | Manager assigns | Assignee has `ticket.assigned` | ✅ `test_assignment_notifies_the_assignee` |
| S-N-03 | FR-7.1 | Reassignment notifies the new assignee | A → B | `ticket.reassigned` for B | ✅ `test_reassignment_notifies_the_new_assignee` |
| S-N-04 | FR-7.1 | Status change notifies reporter + assignee, not the actor | Manager triages | Both have rows; manager does not | ✅ `test_status_change_notifies_reporter_and_assignee_but_not_the_actor` |
| S-N-05 | FR-7.1 | Resolution has its own event type | → `RESOLVED` | `ticket.resolved` (not `status_changed`) | ✅ `test_resolution_produces_a_specific_event_type` |
| S-N-06 | FR-7.3 | **No duplicate row for the same event** | `notify()` twice with the same key | The second call creates nothing | ✅ `test_the_same_event_does_not_produce_a_second_row` |
| S-N-07 | FR-7.3 | Actor is never self-notified | Actor in the recipient list | Skipped | ✅ `test_the_actor_is_never_notified_about_their_own_action` |
| S-N-08 | FR-7.3 | Inactive recipients are skipped | `is_active=False` | Skipped | ✅ `test_inactive_recipients_are_skipped` |
| S-N-09 | FR-7.2 | Delivery marks the row sent | Task runs | `is_sent`, `sent_at` set | ✅ `test_delivery_marks_the_row_as_sent` |
| S-N-10 | FR-7.3 | Task run twice | `send_notification` again | `already-sent`; still one row | ✅ `test_running_the_task_twice_is_a_no_op` |
| S-N-11 | FR-7.3 | Periodic re-drive | Unsent row older than 5 min | `retry_unsent_notifications` sends it | ✅ `test_retry_task_redrives_unsent_notifications` |
| S-N-12 | **real worker** | Task consumed by a separate process | Stack running; assign a ticket | Worker log: task `received` then `succeeded: 'sent'`; 0 pending rows | ✅ scripted: `scripts/verify_stack.sh` + CI `compose-stack` job |
| S-N-13 | FR-7.4 | Inbox is private | Two users | Each sees only their own rows | ✅ `test_inbox_only_contains_my_notifications` |
| S-N-14 | FR-7.4 | Unread count + mark read | 1 unread | Count 1 → 0 after marking | ✅ `test_unread_count_and_mark_read`, `test_mark_all_read` |
| S-N-15 | FR-7.5 | Cannot read someone else's notification | Foreign id | `404` | ✅ `test_cannot_read_someone_elses_notification` |
| S-AU-01 | FR-8.3 | Audit trail is immutable | Any event | `save()` on an existing row / `delete()` | `RuntimeError` in both cases | ✅ `test_audit.py::test_an_event_cannot_be_updated`, `test_an_event_cannot_be_deleted` |
| S-AU-02 | FR-8.1 | A rolled-back operation leaves no event | Transaction fails | Attempt a transition, then roll back | No audit row for the failed attempt | ✅ `test_only_an_attempt_that_committed_leaves_an_event` |
| S-AU-03 | FR-8.2 | Event context | — | Inspect an event | actor, object type/id, project, ticket, IP, user agent | ✅ `test_events_capture_actor_object_and_request_context` |
| S-AU-04 | FR-8.4 | Secrets are not stored | Metadata with password/token/api_key | Read the stored event | `<redacted>`; long values truncated | ✅ `test_sensitive_metadata_is_redacted`, `test_long_values_are_truncated` |
| S-AU-05 | FR-8.3 | Audit API is admin-only and read-only | Manager / admin | `GET`, `POST`, `DELETE /audit/` | Manager `403`; admin `200`; `POST`/`DELETE` `405` | ✅ `test_audit_api_is_admin_only`, `test_admin_can_read_the_audit_trail`, `test_audit_api_is_read_only`, `test_audit_api_cannot_delete` |

## 8. Reporting

| ID | Req | Scenario | Steps | Expected result | Coverage |
| --- | --- | --- | --- | --- | --- |
| S-R-01 | FR-9.1 | Dashboard totals | 3 tickets (new, resolved, blocked) | `GET /reports/dashboard/` | total 3, open 2, resolved 1, blocked 1; zeroes filled in for unused severities | ✅ `test_reports.py::test_dashboard_totals_and_breakdowns` |
| S-R-02 | FR-9.5 | No leakage | Two projects, caller in one | Dashboard | Only the visible project is counted | ✅ `test_dashboard_never_counts_invisible_projects` |
| S-R-03 | FR-9.1 | Filter by project | `?project=<id>` | Only that project | ✅ `test_dashboard_can_be_filtered_by_project` |
| S-R-04 | NFR-1.3 | Foreign project id in the filter | `?project=<foreign>` | Cannot widen the result set — returns 0 | ✅ `test_dashboard_ignores_project_ids_the_caller_cannot_see` |
| S-R-05 | FR-9.3 | Workload includes idle engineers | One engineer with a ticket, a manager with none | `GET /reports/workload/` | Both present; the manager shows 0 | ✅ `test_workload_includes_engineers_with_no_tickets` |
| S-R-06 | FR-9.3 | My workload | — | `GET /reports/my-workload/` | Open/total counts | ✅ `test_my_workload` |
| S-R-07 | FR-9.4 | Activity feed is scoped | Events in two projects | `GET /reports/recent-activity/` | Only the visible project's events | ✅ `test_recent_activity_is_scoped_to_visible_projects` |
| S-R-08 | FR-9.4 | Limit is bounded | `?limit=2` | 2 rows | ✅ `test_recent_activity_limit_is_bounded` |
| S-R-09 | NFR-1.1 | User with no memberships | New account | Dashboard | All zeros, `project_count: 0` | ✅ `test_a_user_without_memberships_sees_empty_reports` |
| S-R-10 | — | Reports screen in the UI | Stack running | Open `/reports` | Charts match the API numbers; workload table lists engineers | 🖐 manual |

## 9. End-to-end (stack) scenarios

These are the "does the whole thing work" checks. They are scripted in
`scripts/verify_stack.sh` and run by CI on every push (`compose-stack` job), and can be reproduced
by hand during the presentation.

| ID | Scenario | Command | Expected result |
| --- | --- | --- | --- |
| S-E2E-01 | Every service starts | `docker compose up -d --build` | 7 services; all healthy (or intentionally unmonitored for `beat`) |
| S-E2E-02 | Health through Nginx | `curl localhost:PORT/health/` | `{"status":"ok","checks":{"database":"ok","cache_backend":"redis","redis":"ok"}}` |
| S-E2E-03 | SPA is served | `curl localhost:PORT/` | `200` with `<div id="root">` |
| S-E2E-04 | Login through the same origin | `POST /api/v1/auth/login/` with a cookie jar | `200`; `sessionid` `HttpOnly` |
| S-E2E-05 | Reads work | tickets, transitions, dashboard | 6 seeded tickets, allowed moves, totals |
| S-E2E-06 | Attachment round trip through S3 | upload → download | bytes identical; object stored under a random key; no public URL |
| S-E2E-07 | Real background worker | assign a ticket, then `docker compose logs worker` | task `received` → `succeeded: 'sent'`; 0 pending notifications |
| S-E2E-08 | Security spot checks | anonymous `/auth/me/`; manager `/audit/` | `403`, `403` |

## 10. Not covered, and why

| Area | Status | Reason / how to close it |
| --- | --- | --- |
| Browser rendering, keyboard navigation, responsive layout | ⛔ gap | No headless browser run was set up. All API paths these screens use are covered. Closing it: a Playwright job (login → dashboard → ticket → transition) in CI. |
| Object persistence across a container restart | ⛔ gap | The shipped S3 mock keeps objects in memory. Use MinIO/SeaweedFS/S3 for durable storage. |
| TLS, HSTS, load balancing | ⛔ gap | The stack serves plain HTTP and expects an edge terminator. |
| Email/SMS delivery | ⛔ gap | Notifications are in-app only; the transport seam exists (`send_notification`) but no provider is configured (assumption A-10). |
| Load/performance testing | ⛔ gap | Indexes and N+1 avoidance are reviewed and asserted by design, but no k6/Locust run was made. |
| Migration rollback | ⛔ gap | Migrations are forward-only; a rollback path would need a documented plan per release. |

## 11. Mapping to requirements

| Requirement group | Scenarios |
| --- | --- |
| FR-1 authentication and identity | S-A-01 … S-A-19 |
| FR-2 projects and membership | S-P-01 … S-P-24 |
| FR-3 tickets | S-T-01 … S-T-28 |
| FR-4 assignment | S-AS-01 … S-AS-11 |
| FR-5 workflow | S-W-01 … S-W-22 |
| FR-6 collaboration | S-C-01 … S-C-20 |
| FR-7 notifications | S-N-01 … S-N-15 |
| FR-8 audit | S-AU-01 … S-AU-05 |
| FR-9 reporting | S-R-01 … S-R-10 |
| NFR security / performance | S-A-08, S-A-15, S-P-06, S-P-19, S-T-19, S-C-11 … S-C-18, S-R-02, S-R-04 |
| End-to-end | S-E2E-01 … S-E2E-08 |