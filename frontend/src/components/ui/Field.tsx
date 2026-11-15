/**
 * Form fields.
 *
 * Each field renders its own label, hint and error, and takes `error` as a plain string so
 * react-hook-form's `formState.errors[x]?.message` can be passed straight through. Server-side
 * field errors from the `ApiError` envelope are fed into the same prop by the `applyFieldErrors`
 * helper below, which is what makes a 400 response appear under the right input rather than only
 * as a toast.
 */

import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import type { ApiError } from '../../lib/http'

interface FieldShellProps {
  id: string
  label?: ReactNode
  hint?: ReactNode
  error?: string
  required?: boolean
  children: ReactNode
}

function FieldShell({ id, label, hint, error, required, children }: FieldShellProps) {
  return (
    <div className={`field${error ? ' field--invalid' : ''}`}>
      {/* An empty-string label means "this select is labelled elsewhere"; render nothing rather
          than an empty `<label>` box that adds vertical space. */}
      {label ? (
        <label className="field__label" htmlFor={id}>
          {label}
          {required ? <span className="field__required" aria-hidden="true">*</span> : null}
        </label>
      ) : null}
      {children}
      {error ? (
        <span className="field__error" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span className="field__hint">{hint}</span>
      ) : null}
    </div>
  )
}

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'className'> {
  label?: ReactNode
  hint?: ReactNode
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, required, id, ...rest },
  ref,
) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  return (
    <FieldShell id={inputId} label={label} hint={hint} error={error} required={required}>
      <input
        ref={ref}
        id={inputId}
        className="input"
        aria-invalid={error ? true : undefined}
        required={required}
        {...rest}
      />
    </FieldShell>
  )
})

export interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'className'> {
  label?: ReactNode
  hint?: ReactNode
  error?: string
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, required, id, rows = 5, ...rest },
  ref,
) {
  const generatedId = useId()
  const textareaId = id ?? generatedId
  return (
    <FieldShell id={textareaId} label={label} hint={hint} error={error} required={required}>
      <textarea
        ref={ref}
        id={textareaId}
        className="textarea"
        rows={rows}
        aria-invalid={error ? true : undefined}
        required={required}
        {...rest}
      />
    </FieldShell>
  )
})

export interface SelectOption {
  value: string
  label: string
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'className' | 'children'> {
  label?: ReactNode
  hint?: ReactNode
  error?: string
  options: SelectOption[]
  /** Rendered as a disabled first option with an empty value. */
  placeholder?: string
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, required, id, options, placeholder, ...rest },
  ref,
) {
  const generatedId = useId()
  const selectId = id ?? generatedId
  return (
    <FieldShell id={selectId} label={label} hint={hint} error={error} required={required}>
      <select
        ref={ref}
        id={selectId}
        className="select"
        aria-invalid={error ? true : undefined}
        required={required}
        {...rest}
      >
        {placeholder ? (
          <option value="" disabled>
            {placeholder}
          </option>
        ) : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldShell>
  )
})

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'className' | 'type'> {
  label: ReactNode
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, id, ...rest },
  ref,
) {
  const generatedId = useId()
  const checkboxId = id ?? generatedId
  return (
    <label className="checkbox" htmlFor={checkboxId}>
      <input ref={ref} id={checkboxId} type="checkbox" {...rest} />
      <span>{label}</span>
    </label>
  )
})

/**
 * Copy the `fields` map of an error envelope into react-hook-form.
 *
 * Keys may be dotted for nested payloads (`profile.timezone`); `setError` understands that path
 * syntax directly, so no key rewriting is needed. A `non_field_errors` entry has nowhere to go on
 * a form, which is why it is skipped and left to the banner that shows `detail`.
 *
 * The setter is typed structurally rather than as `UseFormSetError<T>` so the helper works with any
 * form in the app without threading the form's value type through as a generic parameter — the
 * runtime behaviour is identical.
 */
export interface FieldErrorSetter {
  (name: string, error: { type: string; message: string }): void
}

export function applyFieldErrors(error: unknown, setError: unknown): void {
  if (!(error instanceof Object) || !('fields' in error)) return
  const fields = (error as ApiError).fields
  if (!fields) return
  const set = setError as FieldErrorSetter
  for (const [name, messages] of Object.entries(fields)) {
    if (name === 'non_field_errors' || messages.length === 0) continue
    set(name, { type: 'server', message: messages[0] })
  }
}
