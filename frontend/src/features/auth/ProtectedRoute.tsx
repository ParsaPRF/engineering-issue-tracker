/**
 * Route guards and role gating.
 *
 * `ProtectedRoute` answers "is there a session?" and remembers where the user was headed
 * (`/login?next=…`) so login returns them there. `RoleGate` answers "should this control be
 * rendered for this role?" — a *presentation* decision only.
 *
 * Neither one is a security boundary: the API scopes every queryset and re-checks every capability,
 * so hiding a button only prevents a pointless round trip that would end in a 403. Treating these
 * components as protection would be the mistake this comment exists to prevent.
 */

import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthContext } from './hooks/useAuthContext'
import { ErrorState, LoadingState } from '../../components/ui/States'
import type { ProjectRole, SystemRole } from '../../types/api'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, error } = useAuthContext()
  const location = useLocation()

  if (isLoading) return <LoadingState label="Checking your session…" />

  if (error?.kind === 'failed') {
    // A session probe that failed for a reason other than "anonymous" is not a login problem;
    // sending the user to /login would just fail again with the same error.
    return <ErrorState title="Could not verify your session" error={error.error} />
  }

  if (!isAuthenticated) {
    const next = `${location.pathname}${location.search}`
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
  }

  return <>{children}</>
}

/** Redirect an already-authenticated visitor away from /login and /register. */
export function PublicOnlyRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthContext()
  const location = useLocation()

  if (isLoading) return <LoadingState label="Checking your session…" />
  if (isAuthenticated) {
    const params = new URLSearchParams(location.search)
    const next = params.get('next')
    return <Navigate to={next && next.startsWith('/') ? next : '/'} replace />
  }
  return <>{children}</>
}

export interface RoleGateProps {
  /** Structured role requirement; at least one entry must match. */
  allow?: {
    system?: SystemRole[]
    /** Project roles, matched against the user's own membership summary. */
    project?: ProjectRole[]
  }
  /** Rendered when the requirement is not met. Defaults to nothing. */
  fallback?: ReactNode
  children: ReactNode
}

/**
 * Render `children` only when the caller's role (system role, or their own project role) matches.
 *
 * Only the *caller's own* memberships are known to the client (`GET /auth/me/` exposes them and
 * nothing else), so a `project` requirement is evaluated against the user's highest project role
 * across all their memberships. That is a coarse check on purpose: the precise per-project check
 * happens on the server, where the membership is looked up for the actual project.
 */
export function RoleGate({ allow, fallback = null, children }: RoleGateProps) {
  const { user } = useAuthContext()
  if (!user) return <>{fallback}</>
  if (!allow) return <>{children}</>

  const systemOk = allow.system ? allow.system.includes(user.system_role) : false

  const projectOk = allow.project
    ? user.memberships.some((membership) => membership.is_active && allow.project?.includes(membership.role))
    : false

  return <>{systemOk || projectOk ? children : fallback}</>
}

/**
 * Admins and project managers — the roles that may open projects, manage membership and search the
 * user directory. This mirrors the backend's `can_create_project`, so the affordance and the rule
 * agree.
 */
export function ManagerOnly({ children, fallback = null }: { children: ReactNode; fallback?: ReactNode }) {
  return (
    <RoleGate allow={{ system: ['ADMIN', 'PROJECT_MANAGER'] }} fallback={fallback}>
      {children}
    </RoleGate>
  )
}
