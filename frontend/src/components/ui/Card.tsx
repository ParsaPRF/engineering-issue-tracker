/**
 * Card, page header, tabs, stat card and the small structural pieces screens are assembled from.
 *
 * These are intentionally dumb: no data fetching, no state. Every screen that looks "designed"
 * looks that way because it composes these, which is what keeps the visual language consistent
 * without a component library.
 */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { initials } from '../../lib/format'

export interface CardProps {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  footer?: ReactNode
  /** Removes body padding — use for a table or a feed that meets the card edge. */
  flush?: boolean
  children: ReactNode
}

export function Card({ title, subtitle, actions, footer, flush = false, children }: CardProps) {
  const hasHeader = Boolean(title || subtitle || actions)
  return (
    <section className="card">
      {hasHeader ? (
        <header className="card__header">
          <div className="card__header-main">
            {title ? <h2 className="card__title">{title}</h2> : null}
            {subtitle ? <p className="card__subtitle">{subtitle}</p> : null}
          </div>
          {actions ? <div className="card__actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className={`card__body${flush ? ' card__body--flush' : ''}`}>{children}</div>
      {footer ? <footer className="card__footer">{footer}</footer> : null}
    </section>
  )
}

export interface PageHeaderProps {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  breadcrumbs?: Array<{ label: string; to?: string }>
}

export function PageHeader({ title, subtitle, actions, breadcrumbs }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div className="page-header__main">
        {breadcrumbs && breadcrumbs.length > 0 ? (
          <nav className="breadcrumbs" aria-label="Breadcrumb">
            {breadcrumbs.map((crumb, index) => (
              <span key={`${crumb.label}-${index}`} className="row row--nowrap">
                {index > 0 ? <span className="breadcrumbs__sep" aria-hidden="true">/</span> : null}
                {crumb.to ? <Link to={crumb.to}>{crumb.label}</Link> : <span>{crumb.label}</span>}
              </span>
            ))}
          </nav>
        ) : null}
        <div className="page-header__title">
          <h1>{title}</h1>
        </div>
        {subtitle ? <p className="page-header__subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </div>
  )
}

export interface StatCardProps {
  label: string
  value: ReactNode
  meta?: ReactNode
  accent?: 'none' | 'accent' | 'danger' | 'success' | 'warning'
}

export function StatCard({ label, value, meta, accent = 'none' }: StatCardProps) {
  const accentClass = accent === 'none' ? '' : ` stat-card--${accent}`
  return (
    <div className={`stat-card${accentClass}`}>
      <span className="stat-card__label">{label}</span>
      <span className="stat-card__value">{value}</span>
      {meta ? <span className="stat-card__meta">{meta}</span> : null}
    </div>
  )
}

export interface TabDefinition {
  id: string
  label: string
  count?: number
}

/**
 * Tab strip.
 *
 * A tab is a `<button>` plus a query-string parameter, not a nested route: the tab set is small,
 * the panel content is fetched by the same screen, and `?tab=members` survives a refresh and can be
 * linked to directly.
 */
export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: TabDefinition[]
  active: string
  onChange: (id: string) => void
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          className={`tabs__tab${active === tab.id ? ' tabs__tab--active' : ''}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {tab.count !== undefined ? <span className="tabs__count">{tab.count}</span> : null}
        </button>
      ))}
    </div>
  )
}

/** Circular initials bubble. Used for people, not for entities. */
export function Avatar({
  name,
  size = 'md',
  title,
}: {
  name: string | null | undefined
  size?: 'sm' | 'md' | 'lg'
  title?: string
}) {
  const sizeClass = size === 'md' ? '' : ` avatar--${size}`
  return (
    <span className={`avatar${sizeClass}`} title={title ?? name ?? undefined} aria-hidden="true">
      {initials(name)}
    </span>
  )
}

/** `label — value` row used by the ticket metadata panel and the profile summary. */
export function MetaRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="meta-list__row">
      <span className="meta-list__label">{label}</span>
      <span className="meta-list__value">{children}</span>
    </div>
  )
}

/** Two-line table cell: a primary line with an optional muted second line. */
export function CellStack({ primary, secondary }: { primary: ReactNode; secondary?: ReactNode }) {
  return (
    <span className="cell-stack">
      <span className="cell-stack__primary">{primary}</span>
      {secondary ? <span className="cell-stack__secondary">{secondary}</span> : null}
    </span>
  )
}
