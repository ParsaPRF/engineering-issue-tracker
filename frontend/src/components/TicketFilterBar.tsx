/**
 * The ticket filter bar.
 *
 * Selects are built from `GET /tickets/choices/` rather than from hard-coded arrays, so adding a
 * status or a priority in the backend shows up here without a frontend change. Until that query
 * resolves the selects are empty rather than wrong.
 *
 * Shared by the global ticket list and a project's Tickets tab; the project-scoped variant simply
 * omits the project selector and hides the assignee/component pickers when their source data is not
 * loaded yet.
 */

import { useEffect, useState } from 'react'
import { Button } from './ui/Button'
import { Checkbox, Input, Select } from './ui/Field'
import { MultiSelect } from './ui/MultiSelect'
import { countActiveTicketFilters, TICKET_ORDERING_OPTIONS } from '../features/tickets/filters'
import { useTicketChoices } from '../features/tickets/hooks'
import type { TicketFilterState } from './filterTypes'
import type { Component, Label, ProjectMembership } from '../types/api'

export interface TicketFilterBarProps {
  filters: TicketFilterState
  /**
   * Applied on change. Takes `(key, value)` rather than a generic typed signature because the setter
   * converts per key at runtime (see `useTicketFilters`).
   */
  onChange: (key: string, value: unknown) => void
  onReset: () => void
  /** Members of the selected project, for the assignee filter. Empty disables that control. */
  members?: ProjectMembership[]
  components?: Component[]
  labels?: Label[]
}

export function TicketFilterBar({
  filters,
  onChange,
  onReset,
  members = [],
  components = [],
  labels = [],
}: TicketFilterBarProps) {
  const choices = useTicketChoices()
  const [searchDraft, setSearchDraft] = useState(filters.search)

  // Keep the input in step when the URL changes underneath it (back button, a shared link).
  useEffect(() => {
    setSearchDraft(filters.search)
  }, [filters.search])

  const activeCount = countActiveTicketFilters(filters)

  const statusOptions = (choices.data?.statuses ?? []).map((choice) => ({
    value: choice.value,
    label: choice.label,
  }))
  const priorityOptions = (choices.data?.priorities ?? []).map((choice) => ({
    value: choice.value,
    label: choice.label,
  }))
  const severityOptions = (choices.data?.severities ?? []).map((choice) => ({
    value: choice.value,
    label: choice.label,
  }))
  const typeOptions = (choices.data?.types ?? []).map((choice) => ({
    value: choice.value,
    label: choice.label,
  }))

  const assigneeOptions = [
    { value: '', label: 'Anyone' },
    ...members
      .filter((member) => member.is_active)
      .map((member) => ({ value: member.user.id, label: member.user_name })),
  ]

  const componentOptions = [
    { value: '', label: 'Any component' },
    ...components.map((component) => ({ value: component.id, label: component.name })),
  ]

  const labelOptions = [
    { value: '', label: 'Any label' },
    ...labels.map((label) => ({ value: label.name, label: label.name })),
  ]

  return (
    <>
      <form
        className="toolbar"
        role="search"
        onSubmit={(event) => {
          event.preventDefault()
          onChange('search', searchDraft.trim())
        }}
      >
        <div className="toolbar__field toolbar__search">
          <Input
            label="Search"
            type="search"
            placeholder="Key, title or description…"
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
          />
        </div>

        <div className="toolbar__field">
          <MultiSelect
            label="Status"
            options={statusOptions}
            values={filters.status}
            onChange={(values) => onChange('status', values)}
            placeholder="Any status"
          />
        </div>
        <div className="toolbar__field">
          <MultiSelect
            label="Priority"
            options={priorityOptions}
            values={filters.priority}
            onChange={(values) => onChange('priority', values)}
            placeholder="Any priority"
          />
        </div>
        <div className="toolbar__field">
          <MultiSelect
            label="Severity"
            options={severityOptions}
            values={filters.severity}
            onChange={(values) => onChange('severity', values)}
            placeholder="Any severity"
          />
        </div>
        <div className="toolbar__field">
          <MultiSelect
            label="Type"
            options={typeOptions}
            values={filters.type}
            onChange={(values) => onChange('type', values)}
            placeholder="Any type"
          />
        </div>

        <div className="toolbar__field">
          <Select
            label="Assignee"
            options={assigneeOptions}
            value={filters.assignee}
            disabled={assigneeOptions.length <= 1}
            title={assigneeOptions.length <= 1 ? 'Choose a project to filter by assignee.' : undefined}
            onChange={(event) => onChange('assignee', event.target.value)}
          />
        </div>

        {components.length > 0 ? (
          <div className="toolbar__field">
            <Select
              label="Component"
              options={componentOptions}
              value={filters.component}
              onChange={(event) => onChange('component', event.target.value)}
            />
          </div>
        ) : null}

        {/*
          The label filter matches by name *or* id on the backend
          (`TicketFilter.filter_label`), so a select of the project's own labels is the honest
          control here — a free-text box would invite typos that silently match nothing.
        */}
        <div className="toolbar__field">
          <Select
            label="Label"
            options={labelOptions}
            value={filters.label}
            disabled={labelOptions.length <= 1}
            title={labelOptions.length <= 1 ? 'Choose a project to filter by label.' : undefined}
            onChange={(event) => onChange('label', event.target.value)}
          />
        </div>

        <div className="toolbar__field">
          <Select
            label="Sort"
            options={TICKET_ORDERING_OPTIONS}
            value={filters.ordering}
            onChange={(event) => onChange('ordering', event.target.value)}
          />
        </div>

        <div className="toolbar__actions">
          <Button type="submit" variant="secondary">
            Apply
          </Button>
          <Button type="button" variant="ghost" onClick={onReset} disabled={activeCount === 0}>
            Clear{activeCount > 0 ? ` (${activeCount})` : ''}
          </Button>
        </div>
      </form>

      <div className="filter-summary">
        <Checkbox
          label="Open only"
          checked={filters.open_only}
          onChange={(event) => onChange('open_only', event.target.checked)}
        />
        <Checkbox
          label="Overdue"
          checked={filters.overdue}
          onChange={(event) => onChange('overdue', event.target.checked)}
        />
        <Checkbox
          label="Unassigned"
          checked={filters.unassigned}
          onChange={(event) => onChange('unassigned', event.target.checked)}
        />
      </div>
    </>
  )
}
