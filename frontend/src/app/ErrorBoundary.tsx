/**
 * Error boundary.
 *
 * React catches nothing on its own: a render-time exception in a table row blanks the whole app.
 * This boundary keeps the shell on screen and shows the error with a way out, which matters more in
 * a dashboard than a generic "something went wrong" page.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // No console output in shipped code; the error is surfaced to the user instead. A real
    // deployment would forward this to its error reporter here.
    void error
    void info
  }

  override render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="auth-layout">
          <div className="auth-card">
            <h1 className="auth-card__title">Something broke on this screen</h1>
            <p className="auth-card__subtitle">{this.state.error.message}</p>
            <div style={{ marginTop: 'var(--space-5)' }}>
              <button type="button" className="btn btn--primary" onClick={() => window.location.assign('/')}>
                Back to the dashboard
              </button>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
