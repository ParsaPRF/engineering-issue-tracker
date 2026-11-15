/**
 * Cross-cutting domain types.
 *
 * These mirror the backend's serializers field for field. Enumerations are declared as
 * `const` arrays plus a derived union so a loop (rendering a filter) and a type (a `switch`) can
 * both use the same declaration — the alternative, duplicating the list as a type and a value, is
 * how the two drift apart.
 *
 * The UI never *decides* what the values are: ticket statuses, types, priorities and severities
 * come from `GET /tickets/choices/` at runtime. The unions below only type what the API returns.
 */

export type SystemRole = 'ADMIN' | 'PROJECT_MANAGER' | 'ENGINEER' | 'REPORTER'
export type ProjectRole = 'MANAGER' | 'ENGINEER' | 'REPORTER'
export type ProjectStatus = 'ACTIVE' | 'ARCHIVED'

/** Ordered least → most privileged, used to populate selectors and to reason about gating. */
export const SYSTEM_ROLES: SystemRole[] = ['REPORTER', 'ENGINEER', 'PROJECT_MANAGER', 'ADMIN']
export const PROJECT_ROLES: ProjectRole[] = ['REPORTER', 'ENGINEER', 'MANAGER']

/** A choice as returned by the API's `{value, label}` endpoints. */
export interface Choice {
  value: string
  label: string
}

/** The lean user projection embedded in tickets, memberships and comments. */
export interface UserSummary {
  id: string
  email: string
  full_name: string
  system_role: SystemRole
  is_active: boolean
}

export interface UserProfile {
  job_title: string
  phone: string
  timezone: string
  avatar_key: string
  notify_on_assignment: boolean
  notify_on_comment: boolean
  notify_on_status_change: boolean
}

/** The caller's own membership, embedded in `GET /auth/me/`. */
export interface MembershipSummary {
  project_id: string
  project_key: string
  project_name: string
  role: ProjectRole
  is_active: boolean
}

/** `GET /auth/me/` — the full user record including profile and own memberships. */
export interface CurrentUser {
  id: string
  email: string
  full_name: string
  system_role: SystemRole
  is_active: boolean
  date_joined: string
  profile: UserProfile
  memberships: MembershipSummary[]
}

/** An entry in `GET /auth/users/` (admin user management). */
export interface AdminUser extends UserSummary {
  date_joined: string
  profile: UserProfile
  memberships: MembershipSummary[]
}

export interface ProjectRef {
  id: string
  key: string
  name: string
}

export interface ComponentRef {
  id: string
  name: string
}

export interface Project {
  id: string
  key: string
  name: string
  description: string
  status: ProjectStatus
  owner: UserSummary | null
  archived_at: string | null
  created_at: string
  updated_at: string
  member_count: number | null
  ticket_count: number | null
  open_ticket_count: number | null
}

export interface ProjectMembership {
  id: string
  user: UserSummary
  user_name: string
  user_email: string
  role: ProjectRole
  is_active: boolean
  joined_at: string
  created_at: string
}

export interface Component {
  id: string
  project: string
  name: string
  description: string
  lead: UserSummary | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** `GET /projects/<id>/stats/` (the reports project-statistics payload). */
export interface ProjectStats {
  project_id: string
  project_key: string
  project_name: string
  total_tickets: number
  open_tickets: number
  resolved_tickets: number
  closed_tickets: number
  blocked_tickets: number
  unassigned_tickets: number
  by_status: Record<string, number>
  by_priority: Record<string, number>
  by_severity: Record<string, number>
  by_type: Record<string, number>
  done_tickets: number
}

export interface Label {
  id: string
  name: string
  color: string
}

/** The list projection of a ticket (no description, no labels). */
export interface TicketListItem {
  id: string
  key: string
  project: ProjectRef
  component: ComponentRef | null
  title: string
  type: string
  status: string
  priority: string
  severity: string
  reporter: UserSummary | null
  assignee: UserSummary | null
  due_date: string | null
  is_overdue: boolean
  comment_count: number
  attachment_count: number
  created_at: string
  updated_at: string
}

/** The full ticket, returned by detail and by every mutation. */
export interface Ticket extends TicketListItem {
  description: string
  labels: Label[]
  resolved_at: string | null
  closed_at: string | null
}

/** `GET /tickets/choices/` — the enumerations the forms are built from. */
export interface TicketChoices {
  statuses: Choice[]
  types: Choice[]
  priorities: Choice[]
  severities: Choice[]
}

/**
 * One entry of `GET /workflows/transitions/?ticket=<id>`.
 *
 * `available === false` with a non-empty `blocked_by` is the backend explaining *why* a move is
 * currently impossible ("assignee_required"). The UI renders that reason instead of hiding the
 * button, so the user learns the rule rather than wondering where the action went.
 */
export interface AllowedTransition {
  from_status: string
  to_status: string
  label: string
  requires_comment: boolean
  requires_assignee: boolean
  blocked_by: string[]
  available: boolean
}

export interface TicketTransitions {
  ticket_id: string
  current_status: string
  allowed: AllowedTransition[]
}

export interface TicketHistoryEntry {
  id: string
  from_status: string | null
  to_status: string
  changed_by: string
  changed_by_name: string
  comment: string
  created_at: string
}

export interface Comment {
  id: string
  ticket: string
  author: UserSummary | null
  body: string
  is_deleted: boolean
  is_edited: boolean
  edited_at: string | null
  attachment_count: number
  created_at: string
  updated_at: string
}

export interface Attachment {
  id: string
  ticket: string | null
  comment: string | null
  uploader: UserSummary | null
  original_name: string
  content_type: string
  size_bytes: number
  sha256: string
  download_url: string
  created_at: string
}

export interface Notification {
  id: string
  event_type: string
  title: string
  body: string
  actor: string | null
  actor_name: string | null
  ticket: string | null
  ticket_key: string | null
  project: string | null
  project_key: string | null
  payload: Record<string, unknown>
  is_read: boolean
  read_at: string | null
  is_sent: boolean
  created_at: string
}

/** `GET /reports/dashboard/`. Totals plus per-dimension breakdowns. */
export interface DashboardReport {
  totals: TicketTotals
  by_status: Record<string, number>
  by_priority: Record<string, number>
  by_severity: Record<string, number>
  by_type: Record<string, number>
  by_project: ProjectBreakdownRow[]
  project_count: number
}

export interface TicketTotals {
  total_tickets: number
  open_tickets: number
  resolved_tickets: number
  closed_tickets: number
  blocked_tickets: number
  unassigned_tickets: number
}

export interface ProjectBreakdownRow {
  project_id: string
  project_key: string
  project_name: string
  total_tickets: number
  open_tickets: number
}

export interface WorkloadRow {
  user_id: string
  full_name: string
  email: string
  open_tickets: number
  total_tickets: number
  blocked_tickets: number
}

export interface MyWorkload {
  open_tickets: number
  total_tickets: number
  by_status: Record<string, number>
  by_priority: Record<string, number>
}

export interface ActivityEvent {
  id: string
  action: string
  actor: string | null
  project_key: string | null
  ticket_key: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface ProjectOption {
  id: string
  key: string
  name: string
  status: ProjectStatus
  member_count: number | null
  ticket_count: number | null
  open_ticket_count: number | null
}

export interface AuditEvent {
  id: string
  action: string
  actor: string | null
  actor_email: string | null
  actor_name: string | null
  object_type: string
  object_id: string
  project: string | null
  project_key: string | null
  ticket: string | null
  ticket_key: string | null
  metadata: Record<string, unknown>
  ip_address: string | null
  user_agent: string
  created_at: string
}

/** One declared move in the lifecycle catalogue (`GET /workflows/`). */
export interface WorkflowTransitionRule {
  from_status: string
  to_status: string
  label: string
  allowed_project_roles: ProjectRole[]
  allow_assignee: boolean
  requires_comment: boolean
  requires_assignee: boolean
}

export interface WorkflowCatalogue {
  statuses: Choice[]
  transitions: WorkflowTransitionRule[]
  declared_move_count: number
}
