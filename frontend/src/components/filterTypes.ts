/**
 * The prop shape `TicketFilterBar` works against.
 *
 * The bar takes exactly the filter values plus one setter. `setFilter` accepts `unknown` for its
 * value because the runtime implementation branches on the key (list, boolean, or text) and the
 * compiler cannot express that mapping for a dynamic key — the guards in `useTicketFilters` are the
 * real contract, and they are the only place the conversion happens.
 */

import type { TicketFilters } from '../features/tickets/filters'

/** Every filter value the bar displays. */
export interface TicketFilterValues extends TicketFilters {
  /** The project scope, when the screen offers one (`''` means "all projects"). */
  project: string
}

/** A filter setter that validates the value against the key it was given. */
export type TicketFilterSetter = (key: string, value: unknown) => void

export interface TicketFilterState extends TicketFilterValues {
  setFilter: TicketFilterSetter
}
