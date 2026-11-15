/**
 * Auth hooks: the session query and every mutation that changes who the caller is.
 *
 * Session handling rules encoded here:
 *
 * * The session is *derived*, never stored. `useSession` is a react-query query on `/auth/me/`; the
 *   answer is the single source of truth, and the user object lives only in the query cache (memory).
 * * **403 means "not logged in".** The backend answers an anonymous request to `/auth/me/` with 403,
 *   not 401, so `useSession` retries on nothing and classifies a 401/403 from *that path* as
 *   anonymous. A 403 from any other endpoint is a genuine permission denial and must not be read as
 *   a logout.
 * * Every write first awaits `ensureCsrfCookie()`. The cookie is normally primed at boot, but a
 *   login form left open across a server restart would otherwise POST without a token and get a
 *   CSRF failure the user cannot act on.
 * * After a mutation the affected queries are invalidated rather than patched by hand — the brief
 *   extra fetch is worth never showing a value the server did not confirm.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiGet, ensureCsrfCookie, isUnauthenticated } from '../../lib/http'
import { queryKeys } from '../../lib/queryClient'
import { useToast } from '../../components/toast/ToastProvider'
import { authApi, type LoginPayload, type PasswordChangePayload, type RegisterPayload } from './api'
import type { AdminUser, CurrentUser, SystemRole, UserSummary } from '../../types/api'
import type { Paginated } from '../../lib/http'

/**
 * The classified outcome of the session probe.
 *
 * `anonymous` is an expected state; `failed` is a real error (network, 500) that the user should be
 * told about instead of being bounced to a login page that will also fail.
 */
export type AuthFailure = { kind: 'anonymous' } | { kind: 'failed'; error: unknown }

function classifySessionError(error: unknown): AuthFailure {
  if (isUnauthenticated(error)) return { kind: 'anonymous' }
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    // A 403 from `/auth/me/` with an unexpected code still means "no usable session".
    return { kind: 'anonymous' }
  }
  return { kind: 'failed', error }
}

export function useSession() {
  return useQuery<CurrentUser, unknown>({
    queryKey: queryKeys.auth.me,
    queryFn: () => authApi.me(),
    // The session probe is the gate for the whole app: retrying only helps for transient failures,
    // and react-query's own default would retry a 403 and delay the redirect to /login.
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
      return failureCount < 1
    },
    staleTime: 60_000,
  })
}

/** Reduce the session query into the shape `AuthProvider` exposes. */
export function useSessionState() {
  const query = useSession()
  const failure: AuthFailure | null = query.isError ? classifySessionError(query.error) : null
  return { query, failure }
}

/**
 * Log in.
 *
 * On success the returned user seeds the session cache immediately and every other query is
 * invalidated, so a previous account's data cannot linger in the cache if two people use one
 * browser.
 */
export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: LoginPayload) => {
      await ensureCsrfCookie()
      return authApi.login(payload)
    },
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.auth.me, user)
      queryClient.invalidateQueries()
    },
  })
}

export function useRegister() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: RegisterPayload) => {
      await ensureCsrfCookie()
      return authApi.register(payload)
    },
    onSuccess: () => {
      // Registration does not create a session server-side, so the user is sent to /login.
      queryClient.invalidateQueries()
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await ensureCsrfCookie()
      return authApi.logout()
    },
    onSettled: () => {
      // Clear the cached user *and* every feature's cache: the next caller must not see them.
      queryClient.setQueryData(queryKeys.auth.me, null)
      queryClient.clear()
    },
  })
}

/** `PATCH /auth/me/` — profile and display-name edits. */
export function useUpdateMe() {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (payload: Parameters<typeof authApi.updateMe>[0]) => {
      await ensureCsrfCookie()
      return authApi.updateMe(payload)
    },
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.auth.me, user)
      toast.success('Profile updated')
    },
    onError: (error) => {
      toast.error('Could not update profile', errorMessageOf(error))
    },
  })
}

/** `POST /auth/me/password/`. */
export function useChangePassword() {
  const toast = useToast()
  return useMutation({
    mutationFn: async (payload: PasswordChangePayload) => {
      await ensureCsrfCookie()
      return authApi.changePassword(payload)
    },
    onSuccess: () => toast.success('Password changed'),
    onError: (error) => toast.error('Could not change password', errorMessageOf(error)),
  })
}

/** Directory search. Disabled for an empty term (see `UserDirectoryPicker`). */
export function useDirectory(search: string) {
  return useQuery<UserSummary[], unknown>({
    queryKey: queryKeys.directory(search),
    queryFn: () => authApi.directory(search),
    enabled: search.trim().length > 0,
  })
}

/** Admin user list. */
export function useAdminUsers(params: Parameters<typeof authApi.users>[0]) {
  return useQuery<Paginated<AdminUser>, unknown>({
    queryKey: queryKeys.users.list(params),
    queryFn: () => authApi.users(params),
  })
}

/** Admin: change a user's system role, then refresh every list that shows roles. */
export function useChangeUserRole() {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async ({ id, systemRole }: { id: string; systemRole: SystemRole }) => {
      await ensureCsrfCookie()
      return authApi.changeRole(id, systemRole)
    },
    onSuccess: (user) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.list({}) })
      queryClient.invalidateQueries({ queryKey: ['auth', 'users'] })
      toast.success('Role updated', `${user.full_name} is now ${user.system_role}.`)
    },
    onError: (error) => toast.error('Could not change role', errorMessageOf(error)),
  })
}

/** Admin: activate or deactivate an account. */
export function useSetUserActive() {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async ({ id, active }: { id: string; active: boolean }) => {
      await ensureCsrfCookie()
      return active ? authApi.activate(id) : authApi.deactivate(id)
    },
    onSuccess: (user) => {
      queryClient.invalidateQueries({ queryKey: ['auth', 'users'] })
      toast.success(user.is_active ? 'Account activated' : 'Account deactivated', user.full_name)
    },
    onError: (error) => toast.error('Could not change the account', errorMessageOf(error)),
  })
}

/**
 * Unread notification count, polled.
 *
 * A 30-second interval is the deliberate middle ground: the badge is a nudge, not a chat client, and
 * a shorter interval on an endpoint every open tab calls would be the busiest query in the product.
 * `refetchIntervalInBackground` stays false so a parked tab stops polling.
 */
export function useUnreadNotificationCount(enabled: boolean) {
  return useQuery<{ unread: number }, unknown>({
    queryKey: queryKeys.notifications.unreadCount,
    queryFn: () => apiGet<{ unread: number }>('/notifications/unread-count/'),
    enabled,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    staleTime: 15_000,
  })
}

function errorMessageOf(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Please try again.'
}
