/**
 * Table and pagination.
 *
 * The table is deliberately declarative: a screen passes `columns` and `rows`, and gets a
 * horizontally scrollable, labelled table with an optional sort affordance. It does **not** sort or
 * paginate in the browser — ordering and paging are query parameters the backend owns, because the
 * backend knows how to rank `priority` semantically and the client does not.
 */

import type { ReactNode } from 'react'
import { Button } from './Button'

export interface Column<T> {
  /** Stable identity for React keys — never the display label, which can change or repeat. */
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  align?: 'left' | 'right'
  /** `true` for columns that should not wrap (badges, row actions, dates). */
  tight?: boolean
}

export interface TableProps<T> {
  columns: Array<Column<T>>
  rows: T[]
  rowKey: (row: T) => string
  /** Sort state, when the screen supports server-side ordering. */
  ordering?: {
    current: string
    onChange: (field: string) => void
    /** Fields the API will accept in `?ordering=`. */
    sortable: string[]
  }
  /** Rendered while a refetch is in flight, so the table does not collapse to a spinner. */
  refreshing?: boolean
  caption?: string
}

export function Table<T>({ columns, rows, rowKey, ordering, refreshing, caption }: TableProps<T>) {
  return (
    <div className="table-wrap" aria-busy={refreshing ? true : undefined}>
      <table className="table">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => {
              const isSortable = ordering?.sortable.includes(column.key) ?? false
              const isActive = ordering?.current.replace('-', '') === column.key
              const descending = ordering?.current.startsWith('-') ?? false
              return (
                <th
                  key={column.key}
                  scope="col"
                  className={column.align === 'right' ? 'table__cell--numeric' : undefined}
                >
                  {isSortable && ordering ? (
                    <button
                      type="button"
                      className="table__sort"
                      onClick={() => ordering.onChange(column.key)}
                      aria-label={`Sort by ${typeof column.header === 'string' ? column.header : column.key}`}
                    >
                      {column.header}
                      <span
                        className={`table__sort-icon${isActive ? '' : ' table__sort-icon--idle'}`}
                        aria-hidden="true"
                      >
                        {isActive ? (descending ? '▼' : '▲') : '▲'}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={[
                    column.align === 'right' ? 'table__cell--numeric' : '',
                    column.tight ? 'table__cell--tight' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export interface PaginationProps {
  page: number
  totalPages: number
  count: number
  pageSize: number
  onPageChange: (page: number) => void
}

/**
 * Page controls with an explicit "showing X–Y of N" summary.
 *
 * The summary is not decoration: with server-side pagination the user cannot otherwise tell whether
 * a filter matched 3 rows or 3000.
 */
export function Pagination({ page, totalPages, count, pageSize, onPageChange }: PaginationProps) {
  if (count === 0) return null
  const first = (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, count)
  const safeTotalPages = Math.max(totalPages, 1)

  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="pagination__summary">
        Showing {first}–{last} of {count}
      </span>
      <div className="pagination__controls">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
        >
          Previous
        </Button>
        <span className="pagination__page">
          Page {page} of {safeTotalPages}
        </span>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= safeTotalPages}
        >
          Next
        </Button>
      </div>
    </nav>
  )
}
