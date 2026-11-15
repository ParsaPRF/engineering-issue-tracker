/**
 * People pickers and assignment controls.
 *
 * Two distinct jobs, deliberately not merged:
 *
 * * `UserDirectoryPicker` searches `GET /auth/users/directory/`, which **admins and project managers
 *   only** may call. It is used to add a project member.
 * * `AssigneePicker` offers the project's members whose role can carry a ticket — engineers and
 *   managers. Reporters are not assignable by design (the backend's `is_eligible_assignee` refuses
 *   them), so offering them here would be offering a guaranteed 400.
 *
 * Assigning is *not* a PATCH: `PATCH /tickets/<id>/` rejects `assignee` on purpose. Both pickers
 * therefore call the dedicated `POST /tickets/<id>/assign/` through their feature hook.
 */

import { useMemo, useState } from 'react'
import { Button } from './Button'
import { Input, Select } from './Field'
import { Spinner } from './Button'
import { useDirectorySearch } from '../../features/team/hooks'
import { errorMessage } from '../../lib/http'
import { displayName, roleLabel } from '../../lib/format'
import type { ProjectMembership } from '../../types/api'

/**
 * Search the user directory and pick one person.
 *
 * The search is debounced by react-query's key (each distinct term is its own query), and the
 * endpoint's 403 for a non-manager is rendered inline rather than thrown away.
 */
export function UserDirectoryPicker({
  onSelect,
  excludeUserIds = [],
  placeholder = 'Search by name or email…',
}: {
  onSelect: (userId: string) => void
  excludeUserIds?: string[]
  placeholder?: string
}) {
  const [term, setTerm] = useState('')
  // Only query once the user has typed: an empty term would return the first 20 users of the
  // installation, which is both useless and an enumeration surface.
  const [activeTerm, setActiveTerm] = useState('')
  const query = useDirectorySearch(activeTerm)

  const candidates = useMemo(
    () => (query.data ?? []).filter((user) => !excludeUserIds.includes(user.id)),
    [query.data, excludeUserIds],
  )

  return (
    <div className="stack stack--tight">
      <form
        className="row"
        onSubmit={(event) => {
          event.preventDefault()
          setActiveTerm(term.trim())
        }}
      >
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder={placeholder}
          aria-label="Search the user directory"
        />
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>

      {activeTerm === '' ? (
        <p className="field__hint">Enter a name or email to search the directory.</p>
      ) : query.isLoading ? (
        <div className="row">
          <Spinner size={14} />
          <span className="field__hint">Searching…</span>
        </div>
      ) : query.isError ? (
        <p className="field__error" role="alert">
          {errorMessage(query.error)}
        </p>
      ) : candidates.length === 0 ? (
        <p className="field__hint">No matching people.</p>
      ) : (
        <ul className="stack stack--tight">
          {candidates.map((user) => (
            <li key={user.id} className="row row--between">
              <span className="cell-stack">
                <span className="cell-stack__primary">{displayName(user)}</span>
                <span className="cell-stack__secondary">
                  {user.email} · {roleLabel(user.system_role)}
                  {user.is_active ? '' : ' · inactive'}
                </span>
              </span>
              <Button size="sm" variant="primary" onClick={() => onSelect(user.id)}>
                Add
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * Choose the ticket's assignee from the project's members.
 *
 * `value` is the current assignee id (or `''` for unassigned). The placeholder option is an
 * explicit "Unassigned" rather than a disabled prompt, because unassigning is a real operation
 * (`POST /assign/` with `assignee: null`).
 */
export function AssigneePicker({
  members,
  value,
  onChange,
  disabled = false,
  disabledReason,
  loading = false,
  currentUserId,
}: {
  members: ProjectMembership[]
  value: string
  onChange: (userId: string) => void
  disabled?: boolean
  disabledReason?: string
  loading?: boolean
  currentUserId?: string
}) {
  const options = useMemo(() => {
    const eligible = members.filter(
      (member) => member.is_active && (member.role === 'ENGINEER' || member.role === 'MANAGER'),
    )
    return [
      { value: '', label: 'Unassigned' },
      ...eligible.map((member) => ({
        value: member.user.id,
        label: `${displayName(member.user)}${member.user.id === currentUserId ? ' (me)' : ''} · ${roleLabel(member.role)}`,
      })),
    ]
  }, [members, currentUserId])

  return (
    <div className="stack stack--tight">
      <Select
        label="Assignee"
        options={options}
        value={value}
        disabled={disabled || loading}
        title={disabled ? disabledReason : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {disabled && disabledReason ? <span className="field__hint">{disabledReason}</span> : null}
    </div>
  )
}
