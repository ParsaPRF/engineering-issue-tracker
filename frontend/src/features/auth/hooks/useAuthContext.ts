/**
 * Access to the auth context, plus the role helpers screens use.
 *
 * Kept separate from `AuthProvider.tsx` so a screen that only needs "who is signed in?" does not
 * import the provider, and so `hooks.ts` and the provider can both depend on the context without a
 * cycle.
 */

import { useContext } from 'react'
import { AuthContext, type AuthContextValue } from '../context'
import type { ProjectRole, SystemRole } from '../../../types/api'

export function useAuthContext(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuthContext must be used inside <AuthProvider>')
  return context
}

/** Convenience: the signed-in user, or `null`. */
export function useAuthUser() {
  return useAuthContext().user
}

/** The roles that may create projects, manage members and search the directory. */
const MANAGER_ROLES: SystemRole[] = ['ADMIN', 'PROJECT_MANAGER']

export function isAdmin(user: { system_role: SystemRole } | null): boolean {
  return user?.system_role === 'ADMIN'
}

/**
 * The roles that may open a project and search the user directory — the same predicate the backend's
 * `can_create_project` uses, so the affordance and the rule agree.
 */
export function isProjectManager(user: { system_role: SystemRole } | null): boolean {
  return user ? MANAGER_ROLES.includes(user.system_role) : false
}

/**
 * The caller's project role for one project, from their own membership summary.
 *
 * Returns `null` when they are not an active member. Admins bypass membership on the server, so
 * callers that need "can this person act here?" should treat an admin as a manager — see
 * `canManageProject`.
 */
export function useProjectRole(projectId: string | undefined): ProjectRole | null {
  const user = useAuthUser()
  if (!user || !projectId) return null
  const membership = user.memberships.find(
    (entry) => entry.project_id === projectId && entry.is_active,
  )
  return membership?.role ?? null
}

/**
 * Whether the *UI* should offer project management controls.
 *
 * UI-level only: the backend's `can_manage_project` is the authority and also allows the project's
 * owner, which this cannot know without fetching the project's memberships.
 */
export function canManageProject(
  user: { system_role: SystemRole } | null,
  projectRole: ProjectRole | null,
): boolean {
  if (isAdmin(user)) return true
  return projectRole === 'MANAGER'
}
