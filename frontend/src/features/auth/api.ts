/**
 * Authentication API calls.
 *
 * Session cookie auth: `login` sets the session server-side and we only ever keep the returned
 * user object in memory. There is no token to store, and `localStorage` is never touched — a
 * requirement, not a preference.
 */

import { apiGet, apiPost, apiRequest } from '../../lib/http'
import type { AdminUser, CurrentUser, SystemRole, UserSummary } from '../../types/api'
import type { Paginated } from '../../lib/http'

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload {
  email: string
  full_name: string
  password: string
  password_confirm: string
}

export interface MeUpdatePayload {
  full_name?: string
  profile?: {
    job_title?: string
    phone?: string
    timezone?: string
    notify_on_assignment?: boolean
    notify_on_comment?: boolean
    notify_on_status_change?: boolean
  }
}

export interface PasswordChangePayload {
  current_password: string
  new_password: string
  new_password_confirm: string
}

export const authApi = {
  /** `GET /auth/me/` — the session probe. A 403 here means "not logged in". */
  me: () => apiGet<CurrentUser>('/auth/me/'),

  /** `POST /auth/login/` — returns the user; the server sets the session cookie. */
  login: (payload: LoginPayload) => apiPost<CurrentUser>('/auth/login/', payload),

  /** `POST /auth/register/` — self-registration, lands as a REPORTER. */
  register: (payload: RegisterPayload) => apiPost<CurrentUser>('/auth/register/', payload),

  /** `POST /auth/logout/` — 204, session destroyed server-side. */
  logout: () => apiPost<void>('/auth/logout/'),

  /** `PATCH /auth/me/` — full name and/or nested profile fields. */
  updateMe: (payload: MeUpdatePayload) => apiRequest<CurrentUser>('/auth/me/', { method: 'PATCH', body: payload }),

  /** `POST /auth/me/password/` — 204; the current session is re-established by the server. */
  changePassword: (payload: PasswordChangePayload) => apiPost<void>('/auth/me/password/', payload),

  /** `GET /auth/users/directory/?search=` — array (not paginated). Managers and admins only. */
  directory: (search: string) =>
    apiGet<UserSummary[]>('/auth/users/directory/', search ? { search } : undefined),

  /** `GET /auth/users/` — paginated, admin only. */
  users: (params: { page?: number; page_size?: number; search?: string; ordering?: string; system_role?: string; is_active?: boolean }) =>
    apiGet<Paginated<AdminUser>>('/auth/users/', params),

  /** `PATCH /auth/users/<id>/role/` — admin only. */
  changeRole: (id: string, system_role: SystemRole) =>
    apiRequest<AdminUser>(`/auth/users/${id}/role/`, { method: 'PATCH', body: { system_role } }),

  /** `POST /auth/users/<id>/activate/`. */
  activate: (id: string) => apiPost<AdminUser>(`/auth/users/${id}/activate/`),

  /** `POST /auth/users/<id>/deactivate/`. */
  deactivate: (id: string) => apiPost<AdminUser>(`/auth/users/${id}/deactivate/`),
}
