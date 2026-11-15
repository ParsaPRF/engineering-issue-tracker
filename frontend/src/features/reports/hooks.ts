/**
 * Report, audit and directory hooks.
 *
 * Reports are read-only projections of data the caller can already see — every selector behind them
 * is scoped to the caller's visible projects — so there is nothing to authorise client-side and no
 * mutation ends up in this module.
 *
 * The project filter lives in the *query string*: `/reports/dashboard/?project=<id>` narrows the
 * numbers, and `projectIds` is part of the query key so switching projects refetches instead of
 * showing a cached answer for a different filter.
 */

import { useQuery } from '@tanstack/react-query'
import { apiGet, type Paginated } from '../../lib/http'
import { queryKeys } from '../../lib/queryClient'
import type {
  ActivityEvent,
  AuditEvent,
  DashboardReport,
  MyWorkload,
  ProjectOption,
  UserSummary,
  WorkloadRow,
} from '../../types/api'

export interface ReportsApi {
  dashboard: (projectIds: string[]) => Promise<DashboardReport>
  workload: (projectIds: string[]) => Promise<{ results: WorkloadRow[] }>
  myWorkload: () => Promise<MyWorkload>
  recentActivity: (limit: number) => Promise<{ results: ActivityEvent[] }>
  projects: () => Promise<{ results: ProjectOption[] }>
}

export const reportsApi: ReportsApi = {
  dashboard: (projectIds) =>
    apiGet<DashboardReport>('/reports/dashboard/', projectIds.length > 0 ? { project: projectIds } : undefined),

  workload: (projectIds) =>
    apiGet<{ results: WorkloadRow[] }>('/reports/workload/', projectIds.length > 0 ? { project: projectIds } : undefined),

  myWorkload: () => apiGet<MyWorkload>('/reports/my-workload/'),

  recentActivity: (limit) => apiGet<{ results: ActivityEvent[] }>('/reports/recent-activity/', { limit }),

  projects: () => apiGet<{ results: ProjectOption[] }>('/reports/projects/'),
}

export function useDashboardReport(projectIds: string[]) {
  return useQuery({
    queryKey: queryKeys.reports.dashboard(projectIds),
    queryFn: () => reportsApi.dashboard(projectIds),
  })
}

export function useWorkloadReport(projectIds: string[]) {
  return useQuery({
    queryKey: queryKeys.reports.workload(projectIds),
    queryFn: () => reportsApi.workload(projectIds),
  })
}

export function useMyWorkload() {
  return useQuery({
    queryKey: queryKeys.reports.myWorkload,
    queryFn: () => reportsApi.myWorkload(),
  })
}

export function useRecentActivity(limit = 12) {
  return useQuery({
    queryKey: queryKeys.reports.recentActivity(limit),
    queryFn: () => reportsApi.recentActivity(limit),
  })
}

/** The dashboard's project filter options (id/key/name + counters). */
export function useProjectOptions() {
  return useQuery({
    queryKey: queryKeys.reports.projects,
    queryFn: () => reportsApi.projects(),
    staleTime: 60_000,
  })
}

// -- Audit (admin only) -----------------------------------------------------

export interface AuditListParams {
  page?: number
  page_size?: number
  ordering?: string
  action?: string
  object_type?: string
  project?: string
  ticket?: string
  actor?: string
  /** Query-string values only; the index signature lets the params pass to `apiGet` unchanged. */
  [key: string]: string | number | boolean | undefined
}

/**
 * The full audit trail.
 *
 * Admin-only on the server (`IsAdminUser`), and the screen passes `enabled: false` for a non-admin
 * so it does not fire a request that is certain to 403. Note that this suppresses the *request*, not
 * the *check*: the endpoint is still the authority for anyone who calls it.
 */
export function useAuditEvents(params: AuditListParams, enabled = true) {
  return useQuery({
    queryKey: queryKeys.audit.list(params),
    queryFn: () => apiGet<Paginated<AuditEvent>>('/audit/', params),
    enabled,
    placeholderData: (previous) => previous,
  })
}

// -- Directory --------------------------------------------------------------

/**
 * People search for the team screen's member picker.
 *
 * A thin re-export of the accounts endpoint so the team feature owns its own hook name while the
 * query key stays shared with `useDirectory` — one cache entry, whichever screen asks first.
 */
export function useTeamDirectory(search: string) {
  return useQuery<UserSummary[], unknown>({
    queryKey: queryKeys.directory(search),
    queryFn: () => apiGet<UserSummary[]>('/auth/users/directory/', search ? { search } : undefined),
    enabled: search.trim().length > 0,
  })
}
