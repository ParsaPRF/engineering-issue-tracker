/**
 * Button and the small action affordances built on it.
 *
 * An actionable control that is unavailable carries `title` rather than only being disabled: a
 * transition button that is greyed out has to *say why* it cannot be pressed (the reason comes from
 * the backend's `blocked_by`), otherwise the user is left guessing.
 */

import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'ghost'
  | 'danger'
  | 'danger-ghost'
  | 'link'

export type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className'> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Merged after the variant classes, so a caller can add layout classes (e.g. `topbar__menu`). */
  className?: string
  /** Swaps the label for a spinner and blocks further clicks. */
  loading?: boolean
  /** Square icon-only button; pair with an `aria-label`. */
  iconOnly?: boolean
  fullWidth?: boolean
  children?: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  iconOnly = false,
  fullWidth = false,
  className,
  disabled,
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  const classes = [
    'btn',
    `btn--${variant}`,
    size !== 'md' ? `btn--${size}` : '',
    iconOnly ? 'btn--icon' : '',
    fullWidth ? 'btn--block' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button className={classes} disabled={disabled || loading} type={type} {...rest}>
      {loading ? <Spinner size={size === 'sm' ? 11 : 13} onAccent={variant === 'primary' || variant === 'danger'} /> : null}
      {children}
    </button>
  )
}

/** Round loading indicator. Sizes are inline because the border width must scale with the box. */
export function Spinner({
  size = 16,
  onAccent = false,
  label = 'Loading',
}: {
  size?: number
  onAccent?: boolean
  label?: string
}) {
  return (
    <span
      className={`spinner${onAccent ? ' spinner--on-accent' : ''}`}
      style={{ width: size, height: size }}
      role="status"
      aria-label={label}
    />
  )
}
