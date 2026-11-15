/**
 * Badges.
 *
 * `StatusBadge`, `PriorityBadge` and `SeverityBadge` are separate components even though they share
 * a base, because priority and severity **both contain a `CRITICAL` value**. Rendering them through
 * one component would make two different facts look identical. Each one:
 *
 *  * prefixes the visible label with its axis (`P:` / `S:`) so the two `CRITICAL`s are told apart at
 *    a glance and in a screen reader,
 *  * resolves its colour from its own token ramp (`--priority-*` vs `--severity-*`),
 *  * falls back to a neutral chip for an enum value this build has never heard of.
 */

import type { ReactNode } from 'react'
import { priorityLabel, severityLabel, statusLabel, typeLabel } from '../../lib/format'

export type BadgeTone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'outline'

export interface BadgeProps {
  tone?: BadgeTone
  mono?: boolean
  children: ReactNode
  title?: string
}

export function Badge({ tone = 'neutral', mono = false, children, title }: BadgeProps) {
  return (
    <span className={`badge badge--${tone}${mono ? ' badge--mono' : ''}`} title={title}>
      {children}
    </span>
  )
}

/** Ticket lifecycle state. Colour comes from the `--status-*` ramp, keyed by the enum value. */
export function StatusBadge({ status, title }: { status: string; title?: string }) {
  return (
    <span className={`badge badge--mono chip--status-${status}`} title={title}>
      {statusLabel(status)}
    </span>
  )
}

/**
 * How soon the work is needed. The `P:` prefix disambiguates it from a severity badge — the two
 * axes share the word `CRITICAL`.
 */
export function PriorityBadge({ priority, title }: { priority: string; title?: string }) {
  return (
    <span
      className={`badge badge--mono chip--priority-${priority}`}
      title={title ?? `Priority: ${priorityLabel(priority)}`}
    >
      <span className="badge__axis" aria-hidden="true">
        P:
      </span>
      {priorityLabel(priority)}
    </span>
  )
}

/**
 * How bad the technical impact is. Shares the `CRITICAL` word with priority, so it carries an
 * `S:` prefix and its own colour ramp.
 */
export function SeverityBadge({ severity, title }: { severity: string; title?: string }) {
  return (
    <span
      className={`badge badge--mono chip--severity-${severity}`}
      title={title ?? `Severity: ${severityLabel(severity)}`}
    >
      <span className="badge__axis" aria-hidden="true">
        S:
      </span>
      {severityLabel(severity)}
    </span>
  )
}

const TYPE_TONES: Record<string, BadgeTone> = {
  BUG: 'danger',
  TASK: 'neutral',
  FEATURE: 'accent',
  CHANGE_REQUEST: 'warning',
  SUPPORT: 'outline',
}

export function TypeBadge({ type }: { type: string }) {
  return <Badge tone={TYPE_TONES[type] ?? 'neutral'}>{typeLabel(type)}</Badge>
}

const ROLE_TONES: Record<string, BadgeTone> = {
  ADMIN: 'danger',
  PROJECT_MANAGER: 'accent',
  MANAGER: 'accent',
  ENGINEER: 'neutral',
  REPORTER: 'outline',
}

export function RoleBadge({ role, label }: { role: string; label: string }) {
  return <Badge tone={ROLE_TONES[role] ?? 'neutral'}>{label}</Badge>
}

/** A project label, using the colour the backend stores for it. */
export function LabelBadge({ name, color }: { name: string; color: string }) {
  return (
    <span
      className="badge"
      style={{
        background: `${color}1f`,
        color: shadeForText(color),
        borderColor: `${color}66`,
      }}
      title={name}
    >
      {name}
    </span>
  )
}

/**
 * Darken a stored label colour enough to be legible as text on its own 12%-opacity tint.
 *
 * Label colours are free-form hex from the backend, so this mixes toward black instead of trusting
 * the value to be contrast-safe.
 */
function shadeForText(color: string): string {
  const hex = color.replace('#', '')
  if (hex.length !== 6) return 'var(--color-text-secondary)'
  const red = Number.parseInt(hex.slice(0, 2), 16)
  const green = Number.parseInt(hex.slice(2, 4), 16)
  const blue = Number.parseInt(hex.slice(4, 6), 16)
  if ([red, green, blue].some(Number.isNaN)) return 'var(--color-text-secondary)'
  const mix = (channel: number) => Math.max(0, Math.round(channel * 0.55))
  return `rgb(${mix(red)}, ${mix(green)}, ${mix(blue)})`
}
