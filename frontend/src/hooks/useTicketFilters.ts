/**
 * Ticket filter state.
 *
 * Filters live in the **URL query string**, not in component state. Two reasons that matter:
 *
 * * the dashboard's "Overdue tickets" quick link (`/tickets?overdue=true`) has to arrive with the
 *   filter already applied;
 * * a filtered list is the thing people paste into a ticket or a chat message.
 *
 * The setter's value type is `unknown`: it branches on the key at runtime (comma-joined list,
 * boolean flag, or text) and a static signature cannot express that mapping for a dynamic key. The
 * branching below *is* the contract, and it is the single place the conversion happens.
 */

import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DEFAULT_TICKET_FILTERS, type TicketFilters } from '../features/tickets/filters'
import type { TicketFilterValues } from '../components/filterTypes'

/** Filter keys that hold a comma-separated list. */
const LIST_KEYS: readonly string[] = ['status', 'priority', 'severity', 'type']
/** Filter keys that are booleans in the query string. */
const BOOL_KEYS: readonly string[] = ['overdue', 'unassigned', 'open_only']

export interface UseTicketFiltersResult extends TicketFilterValues {
  page: number
  setFilter: (key: string, value: unknown) => void
  setPage: (page: number) => void
  reset: () => void
  /** True when the screen owns the project and the user cannot change it. */
  projectLocked: boolean
}

export function useTicketFilters(lockedProject?: string): UseTicketFiltersResult {
  const [searchParams, setSearchParams] = useSearchParams()

  const filters = useMemo<Omit<UseTicketFiltersResult, 'setFilter' | 'setPage' | 'reset' | 'projectLocked'>>(() => {
    const readList = (key: string): string[] => {
      const raw = searchParams.get(key)
      if (!raw) return []
      return raw.split(',').filter(Boolean)
    }
    const readBool = (key: string): boolean => searchParams.get(key) === 'true'
    const parsedPage = Number.parseInt(searchParams.get('page') ?? '1', 10)

    return {
      ...DEFAULT_TICKET_FILTERS,
      status: readList('status'),
      priority: readList('priority'),
      severity: readList('severity'),
      type: readList('type'),
      assignee: searchParams.get('assignee') ?? '',
      component: searchParams.get('component') ?? '',
      label: searchParams.get('label') ?? '',
      search: searchParams.get('search') ?? '',
      ordering: searchParams.get('ordering') ?? DEFAULT_TICKET_FILTERS.ordering,
      overdue: readBool('overdue'),
      unassigned: readBool('unassigned'),
      open_only: readBool('open_only'),
      project: lockedProject ?? searchParams.get('project') ?? '',
      page: Number.isNaN(parsedPage) || parsedPage < 1 ? 1 : parsedPage,
    }
  }, [searchParams, lockedProject])

  const setFilter = useCallback(
    (key: string, value: unknown) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current)
          // Any filter change resets to page 1: staying on page 4 of a 2-page result set is the
          // classic "empty list after filtering" bug.
          next.delete('page')

          if (LIST_KEYS.includes(key)) {
            const list = Array.isArray(value) ? value.map(String) : []
            if (list.length === 0) next.delete(key)
            else next.set(key, list.join(','))
            return next
          }
          if (BOOL_KEYS.includes(key)) {
            if (value === true) next.set(key, 'true')
            else next.delete(key)
            return next
          }
          const text = typeof value === 'string' ? value : ''
          const isDefault = text === '' || text === DEFAULT_TICKET_FILTERS[key as keyof TicketFilters]
          if (isDefault) next.delete(key)
          else next.set(key, text)
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const setPage = useCallback(
    (page: number) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current)
          if (page <= 1) next.delete('page')
          else next.set('page', String(page))
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const reset = useCallback(() => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams()
        // Preserve the owning project when a project screen resets its own filters.
        const project = lockedProject ?? current.get('project')
        if (project) next.set('project', project)
        return next
      },
      { replace: true },
    )
  }, [setSearchParams, lockedProject])

  return { ...filters, setFilter, setPage, reset, projectLocked: Boolean(lockedProject) }
}
