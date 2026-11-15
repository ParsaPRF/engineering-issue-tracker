/**
 * Toasts.
 *
 * A tiny store rather than a library: the app needs exactly four things — show a success, show an
 * error, show a neutral note, and auto-dismiss. The mutation hooks call `toast.error(...)` with the
 * `detail` from the `ApiError` envelope, which is why the message always matches what the backend
 * said instead of a generic "Something went wrong".
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

export type ToastTone = 'success' | 'error' | 'info'

export interface Toast {
  id: number
  tone: ToastTone
  title: string
  message?: string
}

interface ToastContextValue {
  toasts: Toast[]
  push: (tone: ToastTone, title: string, message?: string) => void
  dismiss: (id: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

/** How long each tone stays on screen. Errors linger: they usually need reading twice. */
const DISMISS_AFTER_MS: Record<ToastTone, number> = {
  success: 4000,
  info: 5000,
  error: 8000,
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const push = useCallback(
    (tone: ToastTone, title: string, message?: string) => {
      const id = nextId.current++
      setToasts((current) => [...current, { id, tone, title, message }])
      window.setTimeout(() => dismiss(id), DISMISS_AFTER_MS[tone])
    },
    [dismiss],
  )

  const value = useMemo<ToastContextValue>(() => ({ toasts, push, dismiss }), [toasts, push, dismiss])

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>
}

/** Access the toast queue. Throws when used outside `ToastProvider`, which is a wiring bug. */
export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside <ToastProvider>')
  return {
    toasts: context.toasts,
    dismiss: context.dismiss,
    success: (title: string, message?: string) => context.push('success', title, message),
    error: (title: string, message?: string) => context.push('error', title, message),
    info: (title: string, message?: string) => context.push('info', title, message),
  }
}
