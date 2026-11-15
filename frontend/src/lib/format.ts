/**
 * Display formatting.
 *
 * The only interesting decisions live here:
 *
 * * **Priority and severity both contain `CRITICAL`.** They are rendered by different components
 *   (`PriorityBadge` / `SeverityBadge`) which prefix their label (`Priority:` / `Severity:`) for
 *   screen readers and use different colour ramps, so a user never has to guess which axis a red
 *   `CRITICAL` badge belongs to.
 * * **Ordering is semantic.** `PRIORITY_ORDER` / `SEVERITY_ORDER` mirror the backend's rank maps,
 *   so a client-side sort (breakdown bars) agrees with `?ordering=priority`.
 * * **Fallbacks never render "undefined".** Every formatter accepts `null`/`undefined` and returns
 *   an em dash, because a missing due date is information and a blank cell is not.
 */

export const EMPTY = '—'

/** Semantic order, lowest → highest. Matches the backend's `PRIORITY_RANK` / `SEVERITY_RANK`. */
export const PRIORITY_ORDER = ['LOWEST', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const
export const SEVERITY_ORDER = ['TRIVIAL', 'MINOR', 'MAJOR', 'CRITICAL', 'BLOCKER'] as const

/**
 * Status display order, following the lifecycle (capture → triage → work → review → resolve →
 * close) with the detours listed before the terminal states. Alphabetical order would interleave
 * `BLOCKED` between `CLOSED` and `DUPLICATE` and read as noise.
 */
export const STATUS_BAR_ORDER = [
  'NEW',
  'TRIAGED',
  'IN_PROGRESS',
  'IN_REVIEW',
  'BLOCKED',
  'REOPENED',
  'RESOLVED',
  'CLOSED',
  'REJECTED',
  'DUPLICATE',
]

const PRIORITY_LABELS: Record<string, string> = {
  LOWEST: 'Lowest',
  LOW: 'Low',
  MEDIUM: 'Medium',
  HIGH: 'High',
  CRITICAL: 'Critical',
}

const SEVERITY_LABELS: Record<string, string> = {
  TRIVIAL: 'Trivial',
  MINOR: 'Minor',
  MAJOR: 'Major',
  CRITICAL: 'Critical',
  BLOCKER: 'Blocker',
}

const STATUS_LABELS: Record<string, string> = {
  NEW: 'New',
  TRIAGED: 'Triaged',
  IN_PROGRESS: 'In progress',
  IN_REVIEW: 'In review',
  RESOLVED: 'Resolved',
  CLOSED: 'Closed',
  REOPENED: 'Reopened',
  BLOCKED: 'Blocked',
  REJECTED: 'Rejected',
  DUPLICATE: 'Duplicate',
}

const TYPE_LABELS: Record<string, string> = {
  BUG: 'Bug',
  TASK: 'Task',
  FEATURE: 'Feature',
  CHANGE_REQUEST: 'Change request',
  SUPPORT: 'Support request',
}

const ROLE_LABELS: Record<string, string> = {
  ADMIN: 'Administrator',
  PROJECT_MANAGER: 'Project manager',
  ENGINEER: 'Engineer',
  REPORTER: 'Reporter',
  MANAGER: 'Project manager',
}

/**
 * Humanise any enum-ish string: prefer a known label, otherwise title-case the snake case.
 *
 * The fallback matters because the backend can add a status without a frontend release; the UI
 * then shows `SOME_NEW_STATE` as "Some New State" instead of a blank badge.
 */
export function humanise(value: string | null | undefined): string {
  if (!value) return EMPTY
  const known = STATUS_LABELS[value] ?? TYPE_LABELS[value] ?? ROLE_LABELS[value]
  if (known) return known
  return value
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export function statusLabel(value: string | null | undefined): string {
  if (!value) return EMPTY
  return STATUS_LABELS[value] ?? humanise(value)
}

export function typeLabel(value: string | null | undefined): string {
  if (!value) return EMPTY
  return TYPE_LABELS[value] ?? humanise(value)
}

export function priorityLabel(value: string | null | undefined): string {
  if (!value) return EMPTY
  return PRIORITY_LABELS[value] ?? humanise(value)
}

export function severityLabel(value: string | null | undefined): string {
  if (!value) return EMPTY
  return SEVERITY_LABELS[value] ?? humanise(value)
}

export function roleLabel(value: string | null | undefined): string {
  if (!value) return EMPTY
  return ROLE_LABELS[value] ?? humanise(value)
}

/** Semantic rank so a sort puts `CRITICAL` above `LOW`, unlike a string comparison. */
export function priorityRank(value: string): number {
  const index = PRIORITY_ORDER.indexOf(value as (typeof PRIORITY_ORDER)[number])
  return index === -1 ? 0 : index + 1
}

export function severityRank(value: string): number {
  const index = SEVERITY_ORDER.indexOf(value as (typeof SEVERITY_ORDER)[number])
  return index === -1 ? 0 : index + 1
}

/** Parse an API timestamp; the API emits ISO-8601 with an offset. */
export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** `12 Mar 2025`, or an em dash. */
export function formatDate(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return EMPTY
  return date.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
}

/** `12 Mar 2025, 14:05`. */
export function formatDateTime(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return EMPTY
  return date.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** `<input type="date">` wants `YYYY-MM-DD`; the API's `due_date` is exactly that. */
export function toDateInputValue(value: string | null | undefined): string {
  if (!value) return ''
  return value.slice(0, 10)
}

/** `2 hours ago`, falling back to an absolute date beyond a month. */
export function formatRelative(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return EMPTY
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (seconds < 45) return 'just now'

  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['year', 60 * 60 * 24 * 365],
    ['month', 60 * 60 * 24 * 30],
    ['week', 60 * 60 * 24 * 7],
    ['day', 60 * 60 * 24],
    ['hour', 60 * 60],
    ['minute', 60],
  ]
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  for (const [unit, secondsPerUnit] of units) {
    if (seconds >= secondsPerUnit) {
      return formatter.format(-Math.round(seconds / secondsPerUnit), unit)
    }
  }
  return formatter.format(-seconds, 'second')
}

/** `1.4 MB` — binary units, because that is what a file manager shows. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return EMPTY
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`
}

/** Up to two initials for an avatar bubble. */
export function initials(fullName: string | null | undefined): string {
  if (!fullName) return '?'
  const parts = fullName.trim().split(/\s+/).slice(0, 2)
  return parts.map((part) => part.charAt(0).toUpperCase()).join('') || '?'
}

/** Project the caller's own profile fields onto a label. */
export function displayName(user: { full_name?: string | null; email?: string | null } | null | undefined): string {
  if (!user) return EMPTY
  return user.full_name?.trim() || user.email?.trim() || EMPTY
}

/**
 * Percentage of `total`, clamped to 0-100, for the breakdown bars.
 *
 * Returns 0 for an empty total rather than `NaN`, so a bar chart renders nothing instead of
 * crashing the dashboard on a fresh install.
 */
export function percent(value: number, total: number): number {
  if (!total || total <= 0) return 0
  return Math.min(100, Math.round((value / total) * 100))
}

/** Render an audit action (`ticket.status_changed`) as a sentence fragment. */
export function auditActionLabel(action: string | null | undefined): string {
  if (!action) return EMPTY
  const [subject, verb] = action.split('.')
  const subjectLabel = humanise(subject)
  const verbLabel = verb ? verb.replace(/_/g, ' ') : ''
  return verbLabel ? `${subjectLabel} ${verbLabel}` : subjectLabel
}

/**
 * Determine whether a comment is still inside its author's edit window.
 *
 * The authoritative rule is server-side (`COMMENT_EDIT_WINDOW_MINUTES`, enforced in
 * `apps.comments.services.update_comment`). This is a UI affordance only: it decides whether to
 * *offer* the edit control, and the API still rejects a late edit with `edit_window_closed`.
 */
export const COMMENT_EDIT_WINDOW_MINUTES = 30

export function isCommentEditable(
  comment: { author: { id: string } | null; created_at: string; is_deleted: boolean },
  viewerId: string | undefined,
  windowMinutes = COMMENT_EDIT_WINDOW_MINUTES,
): boolean {
  if (comment.is_deleted) return false
  if (!viewerId || comment.author?.id !== viewerId) return false
  const created = parseDate(comment.created_at)
  if (!created) return false
  return Date.now() - created.getTime() < windowMinutes * 60_000
}

/** Plain-text preview of a metadata object for the audit table. */
export function metadataSummary(metadata: Record<string, unknown> | null | undefined): string {
  if (!metadata) return EMPTY
  const entries = Object.entries(metadata)
  if (entries.length === 0) return EMPTY
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`)
    .join(' · ')
}
