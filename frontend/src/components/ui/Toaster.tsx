/**
 * The toast viewport.
 *
 * Mounted once, at the app root. It renders whatever the `ToastProvider` queue holds; nothing else
 * in the app renders a toast, so there is exactly one place where they can appear.
 */

import { useToast, type Toast } from '../toast/ToastProvider'
import { Button } from './Button'

const ICONS: Record<Toast['tone'], string> = {
  success: '✓',
  error: '!',
  info: 'i',
}

export function Toaster() {
  const { toasts, dismiss } = useToast()

  if (toasts.length === 0) return null

  return (
    <div className="toaster" role="region" aria-label="Notifications">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`toast toast--${toast.tone}`}
          role={toast.tone === 'error' ? 'alert' : 'status'}
        >
          <span aria-hidden="true">{ICONS[toast.tone]}</span>
          <div className="toast__main">
            <p className="toast__title">{toast.title}</p>
            {toast.message ? <p className="toast__message">{toast.message}</p> : null}
          </div>
          <Button
            variant="ghost"
            size="sm"
            iconOnly
            aria-label="Dismiss notification"
            onClick={() => dismiss(toast.id)}
          >
            ✕
          </Button>
        </div>
      ))}
    </div>
  )
}
