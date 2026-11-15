/**
 * Project API calls.
 *
 * Projects are never deleted — they are archived and restored (`POST /archive/`, `POST /restore/`),
 * so there is no `remove` here. Components follow the same shape: retired, not destroyed.
 */

import { apiDelete, apiGet, apiPatch, apiPost, type Paginated } from '../../lib/http'
import type { QueryValue } from '../../lib/http'
import type {
  Component,
  Project,
  ProjectMembership,
  ProjectRole,
  ProjectStats,
} from '../../types/api'

/**
 * Params for the project list.
 *
 * The index signature lets the object flow straight into the shared `ListParams`-keyed query cache
 * without a cast: the query key is derived from the params, so any extra key is still part of the
 * identity of the cached result.
 */
export interface ProjectListParams extends Record<string, QueryValue> {
  status?: string
  search?: string
  ordering?: string
  page?: number
  page_size?: number
}

export interface ProjectCreatePayload {
  key: string
  name: string
  description?: string
}

export interface ProjectUpdatePayload {
  name?: string
  description?: string
}

export interface MemberCreatePayload {
  user: string
  role: ProjectRole
}

export interface ComponentCreatePayload {
  name: string
  description?: string
  lead?: string | null
}

export interface ComponentUpdatePayload {
  name?: string
  description?: string
  lead?: string | null
  is_active?: boolean
}

export const projectsApi = {
  list: (params: ProjectListParams) => apiGet<Paginated<Project>>('/projects/', params as Record<string, QueryValue>),

  detail: (id: string) => apiGet<Project>(`/projects/${id}/`),

  create: (payload: ProjectCreatePayload) => apiPost<Project>('/projects/', payload),

  update: (id: string, payload: ProjectUpdatePayload) => apiPatch<Project>(`/projects/${id}/`, payload),

  /** Archive keeps the row and its tickets; the project becomes read-only. */
  archive: (id: string) => apiPost<Project>(`/projects/${id}/archive/`),

  restore: (id: string) => apiPost<Project>(`/projects/${id}/restore/`),

  /** Members are returned as a plain array (not paginated), including inactive ones optionally. */
  members: (id: string, includeInactive = false) =>
    apiGet<ProjectMembership[]>(
      `/projects/${id}/members/`,
      includeInactive ? { include_inactive: 'true' } : undefined,
    ),

  addMember: (id: string, payload: MemberCreatePayload) =>
    apiPost<ProjectMembership>(`/projects/${id}/members/`, payload),

  updateMemberRole: (id: string, membershipId: string, role: ProjectRole) =>
    apiPatch<ProjectMembership>(`/projects/${id}/members/${membershipId}/`, { role }),

  removeMember: (id: string, membershipId: string) =>
    apiDelete(`/projects/${id}/members/${membershipId}/`),

  components: (id: string, includeInactive = false) =>
    apiGet<Component[]>(
      `/projects/${id}/components/`,
      includeInactive ? { include_inactive: 'true' } : undefined,
    ),

  createComponent: (id: string, payload: ComponentCreatePayload) =>
    apiPost<Component>(`/projects/${id}/components/`, payload),

  /**
   * Component updates go through `/components/<id>/`, not the project-nested path — a component
   * belongs to exactly one project, so repeating the project in the URL adds nothing.
   */
  updateComponent: (componentId: string, payload: ComponentUpdatePayload) =>
    apiPatch<Component>(`/components/${componentId}/`, payload),

  deactivateComponent: (componentId: string) =>
    apiPost<Component>(`/components/${componentId}/deactivate/`),

  stats: (id: string) => apiGet<ProjectStats>(`/projects/${id}/stats/`),
}
