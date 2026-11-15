/**
 * Loading / empty / error states.
 *
 * Architecture requirement made concrete: every list and panel renders exactly one of these three,
 * derived from react-query's `isLoading` / `rows.length === 0` / `isError`. The error state always
 * offers a retry wired to the query's own `refetch`, so a transient 500 is one click from recovery
 * instead of a page reload.
 */

import type { ReactNode } from 'react'
import { Spinner } from './Button'
import { errorMessage } from '../../lib/http'

/** Full-panel loading indicator. `label` is announced, not only shown. */
export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="page-loading" role="status">
      <Spinner size={18} />
      <span>{label}</span>
    </div>
  )
}

export interface EmptyStateProps {
  title: string
  message?: ReactNode
  action?: ReactNode
  icon?: ReactNode
  /** Tighter padding for an empty state inside an already-bounded card. */
  inline?: boolean
}

export function EmptyState({ title, message, action, icon, inline = false }: EmptyStateProps) {
  return (
    <div className={`state${inline ? ' state--inline' : ''}`}>
      <div className="state__icon" aria-hidden="true">
        {icon ?? '∅'}
      </div>
      <p className="state__title">{title}</p>
      {message ? <p className="state__message">{message}</p> : null}
      {action ? <div className="state__actions">{action}</div> : null}
    </div>
  )
}

export interface ErrorStateProps {
  title?: string
  error: unknown
  onRetry?: () => void
  inline?: boolean
}

/**
 * Error panel.
 *
 * The message comes from `ApiError.detail`, which is the backend's own sentence — so a 403 says
 * "Only administrators may search the directory" rather than a generic failure.
 */
export function ErrorState({ title = 'Something went wrong', error, onRetry, inline = false }: ErrorStateProps) {
  return (
    <div className={`state state--error${inline ? ' state--inline' : ''}`} role="alert">
      <div className="state__icon" aria-hidden="true">
        !
      </div>
      <p className="state__title">{title}</p>
      <p className="state__message">{errorMessage(error)}</p>
      {onRetry ? (
        <div className="state__actions">
          <button type="button" className="btn btn--secondary btn--sm" onClick={onRetry}>
            Try again
          </button>
        </div>
      ) : null}
    </div>
  )
}

/**
 * Inline form-level alert.
 *
 * Used for the `detail` of a failed mutation, above the form, when the error cannot be attributed
 * to one field — a `code` like `edit_window_closed` has no input to sit under.
 */
export function FormAlert({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <div className="form-alert" role="alert">
      <span aria-hidden="true">!</span>
      <span>{errorMessage(error)}</span>
    </div>
  )
}
