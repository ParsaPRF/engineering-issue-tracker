/**
 * Shared display components: status/priority/severity chips, the breakdown bar, the activity feed,
 * and the comment thread.
 *
 * These live in `components/` rather than inside one feature because more than one feature renders
 * them — the dashboard and the reports screen both show breakdowns, the ticket detail and the
 * project detail both show a ticket table.
 */

import { Link } from 'react-router-dom'
import { PriorityBadge, SeverityBadge, StatusBadge, TypeBadge } from './ui/Badge'
import { Avatar, CellStack } from './ui/Card'
import {
  auditActionLabel,
  displayName,
  formatDate,
  formatDateTime,
  formatRelative,
  humanise,
  percent,
  statusLabel,
} from '../lib/format'
import type { ActivityEvent, TicketListItem } from '../types/api'

/**
 * Breakdown bars for a `{VALUE: count}` map.
 *
 * Values are rendered in the order given by `order` (semantic, e.g. priority low → high) rather than
 * object insertion order, so the bars read as a scale instead of an arbitrary list. Zero-count rows
 * are kept: an empty "Critical" row is information ("nothing is critical"), a missing row looks like
 * a bug.
 */
export function BreakdownBars({
  title,
  data,
  order,
  total,
  toneByValue,
}: {
  title: string
  data: Record<string, number>
  order?: string[]
  total?: number
  toneByValue?: Record<string, string>
}) {
  const entries = Object.entries(data)
  if (entries.length === 0) {
    return <p className="field__hint">No data yet.</p>
  }

  const ordered = order
    ? [...entries].sort((a, b) => {
        const indexA = order.indexOf(a[0])
        const indexB = order.indexOf(b[0])
        return (indexA === -1 ? 999 : indexA) - (indexB === -1 ? 999 : indexB)
      })
    : entries

  const sum = total ?? ordered.reduce((accumulator, [, value]) => accumulator + value, 0)

  return (
    <div className="breakdown" aria-label={title}>
      {ordered.map(([key, value]) => (
        <div className="breakdown__row" key={key}>
          <span className="breakdown__label" title={humanise(key)}>
            {humanise(key)}
          </span>
          <span className="breakdown__track">
            <span
              className={`breakdown__fill breakdown__fill--${toneByValue?.[key] ?? 'accent'}`}
              style={{ width: `${percent(value, sum)}%` }}
              role="presentation"
            />
          </span>
          <span className="breakdown__value">{value}</span>
        </div>
      ))}
    </div>
  )
}

/** Colour per priority value, matching the badge ramp so the chart and the chips agree. */
export const PRIORITY_BAR_TONES: Record<string, string> = {
  LOWEST: 'neutral',
  LOW: 'accent',
  MEDIUM: 'teal',
  HIGH: 'orange',
  CRITICAL: 'danger',
}

export const SEVERITY_BAR_TONES: Record<string, string> = {
  TRIVIAL: 'neutral',
  MINOR: 'success',
  MAJOR: 'warning',
  CRITICAL: 'danger',
  BLOCKER: 'danger',
}

export const STATUS_BAR_TONES: Record<string, string> = {
  NEW: 'accent',
  TRIAGED: 'purple',
  IN_PROGRESS: 'warning',
  IN_REVIEW: 'teal',
  RESOLVED: 'success',
  CLOSED: 'neutral',
  REOPENED: 'orange',
  BLOCKED: 'danger',
  REJECTED: 'neutral',
  DUPLICATE: 'neutral',
}

/** The badge trio shown in tables and headers. Priority and severity stay visually distinct. */
export function TicketBadges({
  status,
  priority,
  severity,
  type,
}: {
  status: string
  priority: string
  severity: string
  type?: string
}) {
  return (
    <span className="row" style={{ gap: 'var(--space-1)' }}>
      <StatusBadge status={status} />
      <PriorityBadge priority={priority} />
      <SeverityBadge severity={severity} />
      {type ? <TypeBadge type={type} /> : null}
    </span>
  )
}

/**
 * The ticket's identity cell: a deep link on the key, with the title beneath.
 *
 * The link targets `/tickets/<id>` — the UUID, not the human key, because the API's lookup is by
 * primary key. The key is shown as the label because that is what people say out loud.
 */
export function TicketLinkCell({ ticket }: { ticket: TicketListItem }) {
  return (
    <CellStack
      primary={<Link to={`/tickets/${ticket.id}`}>{ticket.key}</Link>}
      secondary={ticket.title}
    />
  )
}

/** Assignee cell with an avatar, or an explicit "Unassigned". */
export function AssigneeCell({ ticket }: { ticket: TicketListItem }) {
  if (!ticket.assignee) {
    return <span className="cell-stack__secondary">Unassigned</span>
  }
  return (
    <span className="row row--nowrap">
      <Avatar name={ticket.assignee.full_name} size="sm" />
      <span className="cell-stack__primary" style={{ fontWeight: 400 }}>
        {displayName(ticket.assignee)}
      </span>
    </span>
  )
}

/** Due date, marked late when the ticket is overdue. */
export function DueDateCell({ ticket }: { ticket: TicketListItem }) {
  if (!ticket.due_date) return <span className="cell-stack__secondary">—</span>
  return (
    <span className={ticket.is_overdue ? 'badge badge--danger' : 'cell-stack__secondary'}>
      {formatDate(ticket.due_date)}
    </span>
  )
}

/**
 * Recent-activity feed.
 *
 * Each row names the actor, the action and the object it happened to, and links to the ticket when
 * the event carries a key — the feed is only useful if it is a jump-off point.
 */
export function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <ul className="feed">
      {events.map((event) => (
        <li className="feed__item" key={event.id}>
          <Avatar name={event.actor} size="sm" />
          <div className="feed__main">
            <p className="feed__text">
              <strong>{event.actor ?? 'System'}</strong> · {auditActionLabel(event.action)}
              {event.ticket_key ? (
                <>
                  {' → '}
                  <Link to={`/tickets?search=${encodeURIComponent(event.ticket_key)}`}>{event.ticket_key}</Link>
                </>
              ) : null}
              {event.project_key ? <span className="feed__meta"> in {event.project_key}</span> : null}
            </p>
            <p className="feed__meta" title={formatDateTime(event.created_at)}>
              {formatRelative(event.created_at)}
            </p>
          </div>
        </li>
      ))}
    </ul>
  )
}

/**
 * A single-row stacked bar showing how a total splits across statuses.
 *
 * Used on the dashboard where the shape of the distribution matters more than exact counts; the
 * legend underneath carries the numbers.
 */
export function StatusDistribution({
  data,
  order,
}: {
  data: Record<string, number>
  order?: string[]
}) {
  const entries = Object.entries(data).filter(([, value]) => value > 0)
  if (entries.length === 0) return <p className="field__hint">No tickets yet.</p>

  const ordered = order
    ? [...entries].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))
    : entries
  const total = ordered.reduce((accumulator, [, value]) => accumulator + value, 0)

  const fills: Record<string, string> = {
    neutral: 'var(--grey-400)',
    accent: 'var(--blue-500)',
    success: 'var(--green-600)',
    warning: 'var(--amber-600)',
    danger: 'var(--red-600)',
    purple: 'var(--purple-600)',
    teal: 'var(--teal-600)',
    orange: 'var(--orange-600)',
  }

  return (
    <div>
      <div className="stacked-bar" role="img" aria-label="Ticket status distribution">
        {ordered.map(([key, value]) => (
          <span
            key={key}
            className="stacked-bar__segment"
            style={{
              width: `${(value / total) * 100}%`,
              background: fills[STATUS_BAR_TONES[key] ?? 'neutral'],
            }}
            title={`${statusLabel(key)}: ${value}`}
          />
        ))}
      </div>
      <div className="legend">
        {ordered.map(([key, value]) => (
          <span className="legend__item" key={key}>
            <span
              className="legend__swatch"
              style={{ background: fills[STATUS_BAR_TONES[key] ?? 'neutral'] }}
              aria-hidden="true"
            />
            {statusLabel(key)} · {value}
          </span>
        ))}
      </div>
    </div>
  )
}
