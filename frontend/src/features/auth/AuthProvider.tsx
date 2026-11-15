/**
 * Authentication provider.
 *
 * **The backend is the authority.** Everything here is a UI projection of the answer to one
 * question: "does the server consider this caller signed in?" `RoleGate` and the route guards only
 * decide what to *render*; they never decide what is *allowed*. A user who edits the DOM to reveal a
 * hidden button gets a 403 from the API, because every endpoint re-checks the capability
 * server-side. The gating exists to avoid showing dead controls, not to enforce anything.
 */

import { useCallback, useMemo, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { AuthContext, type AuthContextValue } from './context'
import { useSessionState } from './hooks'
import type { CurrentUser } from '../../types/api'

export function AuthProvider({ children }: { children: ReactNode }) {
  const { query, failure } = useSessionState()
  const queryClient = useQueryClient()

  // "Anonymous" is a valid answer, not a failure: the app must not treat it as an error.
  const isAnonymous = failure?.kind === 'anonymous'
  const user = isAnonymous ? null : (query.data ?? null)

  const setUser = useCallback(
    (next: CurrentUser | null) => {
      queryClient.setQueryData(['auth', 'me'], next)
    },
    [queryClient],
  )

  const refetch = useCallback(() => {
    void query.refetch()
  }, [query])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      // `isLoading` is true only on the first fetch; a background refetch must not unmount the app.
      isLoading: query.isLoading,
      isAuthenticated: user !== null,
      error: failure,
      setUser,
      refetch,
    }),
    [user, query.isLoading, failure, setUser, refetch],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
