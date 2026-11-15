/**
 * Modal dialog.
 *
 * Rendered into `document.body` through a portal so a modal opened from inside a table cell is not
 * clipped by the table's `overflow-x: auto` — a real bug that a non-portalled dialog hits
 * immediately on the ticket list.
 *
 * Accessibility: `role="dialog"` + `aria-modal`, Escape closes, the backdrop is a labelled button so
 * it is reachable by keyboard, focus moves into the dialog on open, and the page behind it cannot
 * scroll.
 */

import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Button } from './Button'

export interface ModalProps {
  open: boolean
  onClose: () => void
  title: ReactNode
  description?: ReactNode
  /** Right-aligned action row. The caller owns submit/loading state. */
  footer?: ReactNode
  size?: 'md' | 'lg'
  children: ReactNode
}

export function Modal({ open, onClose, title, description, footer, size = 'md', children }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    // Move focus in so keyboard users are not left behind the scrim.
    dialogRef.current?.focus()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="modal-scrim">
      <button type="button" className="modal-scrim__backdrop" aria-label="Close dialog" onClick={onClose} />
      <div
        ref={dialogRef}
        className={`modal${size === 'lg' ? ' modal--lg' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="modal__header">
          <div className="modal__title" id={titleId}>
            {title}
            {description ? <p className="modal__description">{description}</p> : null}
          </div>
          <Button variant="ghost" size="sm" iconOnly aria-label="Close" onClick={onClose}>
            ✕
          </Button>
        </header>
        <div className="modal__body">{children}</div>
        {footer ? <footer className="modal__footer">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  )
}

export interface ConfirmDialogProps {
  open: boolean
  title: string
  message: ReactNode
  confirmLabel?: string
  destructive?: boolean
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** A confirm step for consequential actions (remove member, delete comment, archive project). */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  destructive = false,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={loading}>
            Cancel
          </Button>
          <Button variant={destructive ? 'danger' : 'primary'} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="description">{message}</p>
    </Modal>
  )
}
