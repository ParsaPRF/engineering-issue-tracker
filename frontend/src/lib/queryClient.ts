/**
 * The single react-query client plus the app's query-key vocabulary.
 *
 * Two policies are deliberate:
 *
 * * **`retry` refuses to retry client errors.** Retrying a 400 or a 403 just replays a request the
 *   backend already rejected; it delays the error the user needs to see. Only network failures and
 *   5xx responses are retried, which is exactly when a retry can help.
 * * **Errors are surfaced by screens, not by a global handler.** Every list and panel renders its
 *   own error state with a retry button, so a silent toast is not the only signal that something
 *   failed.
 *
 * Query keys are centralised here so an invalidation can never miss because two modules spelled
 * the same key differently.
 */

import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError, type QueryValue } from './http'

function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError) {
    // 4xx is the caller's fault: retrying cannot change the answer.
    if (error.status >= 400 && error.status < 500) return false
    // Network errors (status 0) and 5xx are transient.
  }
  return failureCount < 2
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: shouldRetry,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // Pagination keeps the previous page on screen instead of flashing an empty table.
      placeholderData: (previous: unknown) => previous,
    },
    mutations: {
      // A failed write is never worth replaying automatically: the user should decide.
      retry: false,
    },
  },
  queryCache: new QueryCache({
    onError: () => {
      /* Screens own their error UI; see module docstring. */
    },
  }),
  mutationCache: new MutationCache({
    onError: () => {
      /* Screens own their error UI; see module docstring. */
    },
  }),
})

/** Parameters accepted by the paginated list endpoints. */
export interface ListParams {
  page?: number
  page_size?: number
  search?: string
  ordering?: string
  [key: string]: QueryValue
}

/**
 * Query keys, namespaced by feature.
 *
 * `lists()` / `list(params)` are separate levels so a mutation can invalidate every variation of a
 * list (any filter combination) without knowing which ones are cached.
 */
export const queryKeys = {
  auth: {
    me: ['auth', 'me'] as const,
  },
  directory: (search: string) => ['auth', 'directory', search] as const,
  users: {
    list: (params: ListParams) => ['auth', 'users', 'list', params] as const,
  },
  projects: {
    all: ['projects'] as const,
    lists: () => ['projects', 'list'] as const,
    list: (params: ListParams) => ['projects', 'list', params] as const,
    detail: (id: string) => ['projects', 'detail', id] as const,
    members: (id: string) => ['projects', 'detail', id, 'members'] as const,
    components: (id: string) => ['projects', 'detail', id, 'components'] as const,
    stats: (id: string) => ['projects', 'detail', id, 'stats'] as const,
  },
  tickets: {
    all: ['tickets'] as const,
    lists: () => ['tickets', 'list'] as const,
    list: (params: ListParams) => ['tickets', 'list', params] as const,
    detail: (id: string) => ['tickets', 'detail', id] as const,
    choices: ['tickets', 'choices'] as const,
    transitions: (id: string) => ['tickets', 'transitions', id] as const,
    history: (id: string) => ['tickets', 'history', id] as const,
    comments: (id: string) => ['tickets', 'comments', id] as const,
    attachments: (id: string) => ['tickets', 'attachments', id] as const,
    myAssignments: (includeDone: boolean) => ['tickets', 'my-assignments', includeDone] as const,
  },
  labels: {
    list: (projectId: string) => ['labels', projectId] as const,
  },
  workflows: {
    catalogue: ['workflows', 'catalogue'] as const,
  },
  notifications: {
    list: (unreadOnly: boolean, page: number) => ['notifications', 'list', unreadOnly, page] as const,
    unreadCount: ['notifications', 'unread-count'] as const,
  },
  reports: {
    dashboard: (projectIds: string[]) => ['reports', 'dashboard', projectIds] as const,
    workload: (projectIds: string[]) => ['reports', 'workload', projectIds] as const,
    myWorkload: ['reports', 'my-workload'] as const,
    recentActivity: (limit: number) => ['reports', 'recent-activity', limit] as const,
    projects: ['reports', 'projects'] as const,
  },
  audit: {
    list: (params: ListParams) => ['audit', 'list', params] as const,
  },
}
