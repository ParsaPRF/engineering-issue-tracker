/**
 * The authentication context object.
 *
 * Split out of `AuthProvider.tsx` and `hooks.ts` on purpose: the provider imports the hooks and the
 * hooks import the context, so keeping the context in a leaf module avoids an import cycle that
 * would only surface as a `undefined is not an object` at runtime.
 */

import { createContext } from 'react'
import type { AuthFailure } from './hooks'
import type { CurrentUser } from '../../types/api'

export interface AuthContextValue {
  /** The signed-in user, or `null` when the session probe failed with 401/403. */
  user: CurrentUser | null
  /** `true` while the session probe is in flight — distinct from "not logged in". */
  isLoading: boolean
  isAuthenticated: boolean
  /** The error that ended the session, when it was not a plain "not logged in". */
  error: AuthFailure | null
  /** Replace the cached user (after a profile PATCH, for instance). */
  setUser: (user: CurrentUser | null) => void
  /** Ask the server again whether this session is valid. */
  refetch: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
