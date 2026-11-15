/**
 * Multi-select control for the ticket filter bar.
 *
 * Multi-value filters are comma-separated in the API (`?status=NEW,IN_PROGRESS`), and a plain
 * `<select multiple>` is unusable on a phone, so this is a button that opens a checkbox panel.
 * It closes on outside click and on Escape, and reports the current selection as a summary so the
 * user can see the filter is active without reopening it.
 */

import { useEffect, useId, useRef, useState } from 'react'
import type { SelectOption } from './Field'

export interface MultiSelectProps {
  label: string
  options: SelectOption[]
  values: string[]
  onChange: (values: string[]) => void
  /** Shown on the trigger when nothing is selected. */
  placeholder?: string
  disabled?: boolean
}

export function MultiSelect({
  label,
  options,
  values,
  onChange,
  placeholder = 'Any',
  disabled = false,
}: MultiSelectProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const toggle = (value: string) => {
    onChange(values.includes(value) ? values.filter((item) => item !== value) : [...values, value])
  }

  const summary =
    values.length === 0
      ? placeholder
      : values.length === 1
        ? (options.find((option) => option.value === values[0])?.label ?? values[0])
        : `${values.length} selected`

  return (
    <div className="field" ref={containerRef}>
      <span className="field__label">{label}</span>
      <div className="multiselect">
        <button
          type="button"
          className="input row row--between"
          aria-expanded={open}
          aria-controls={panelId}
          aria-haspopup="listbox"
          disabled={disabled}
          onClick={() => setOpen((current) => !current)}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {summary}
          </span>
          <span aria-hidden="true" style={{ opacity: 0.6 }}>
            ▾
          </span>
        </button>
        {open ? (
          <div className="multiselect__panel" id={panelId} role="listbox" aria-multiselectable="true">
            {options.length === 0 ? (
              <p className="field__hint" style={{ padding: 'var(--space-2)' }}>
                No options available.
              </p>
            ) : (
              options.map((option) => (
                <label key={option.value} className="multiselect__option">
                  <input
                    type="checkbox"
                    checked={values.includes(option.value)}
                    onChange={() => toggle(option.value)}
                  />
                  <span>{option.label}</span>
                </label>
              ))
            )}
            {values.length > 0 ? (
              <button
                type="button"
                className="multiselect__option"
                onClick={() => onChange([])}
                style={{ color: 'var(--color-accent)' }}
              >
                Clear selection
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
