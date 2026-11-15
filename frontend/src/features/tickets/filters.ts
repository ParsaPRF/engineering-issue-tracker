/**
 * The ticket filter vocabulary.
 *
 * `TicketFilterBar` is used by both the global ticket list and a project's Tickets tab, so its shape
 * lives here rather than in either page.
 */

export interface TicketFilters {
  /** Comma-separated in the API (`?status=NEW,IN_PROGRESS`); an array here, joined by `buildQuery`. */
  status: string[]
  priority: string[]
  severity: string[]
  type: string[]
  assignee: string
  component: string
  label: string
  search: string
  ordering: string
  overdue: boolean
  unassigned: boolean
  open_only: boolean
}

export const DEFAULT_TICKET_FILTERS: TicketFilters = {
  status: [],
  priority: [],
  severity: [],
  type: [],
  assignee: '',
  component: '',
  label: '',
  search: '',
  ordering: '-created_at',
  overdue: false,
  unassigned: false,
  open_only: false,
}

/** Ordering choices offered in the toolbar. Values must be in the API's `ordering_fields`. */
export const TICKET_ORDERING_OPTIONS = [
  { value: '-created_at', label: 'Newest first' },
  { value: 'created_at', label: 'Oldest first' },
  { value: '-updated_at', label: 'Recently updated' },
  { value: '-priority', label: 'Priority (high → low)' },
  { value: 'priority', label: 'Priority (low → high)' },
  { value: '-severity', label: 'Severity (high → low)' },
  { value: 'severity', label: 'Severity (low → high)' },
  { value: 'due_date', label: 'Due date (soonest)' },
  { value: '-due_date', label: 'Due date (latest)' },
  { value: 'key', label: 'Ticket key' },
  { value: 'status', label: 'Status' },
]

/** Count the filters that are narrowing the list, for the "N filters active" summary. */
export function countActiveTicketFilters(filters: TicketFilters): number {
  let count = 0
  count += filters.status.length > 0 ? 1 : 0
  count += filters.priority.length > 0 ? 1 : 0
  count += filters.severity.length > 0 ? 1 : 0
  count += filters.type.length > 0 ? 1 : 0
  count += filters.assignee ? 1 : 0
  count += filters.component ? 1 : 0
  count += filters.label ? 1 : 0
  count += filters.search ? 1 : 0
  count += filters.overdue ? 1 : 0
  count += filters.unassigned ? 1 : 0
  count += filters.open_only ? 1 : 0
  return count
}
