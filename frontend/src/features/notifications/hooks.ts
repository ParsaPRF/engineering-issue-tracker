/**
 * Notification hooks.
 *
 * `unread-count` is polled by the topbar (see `useUnreadNotificationCount`), which is why every
 * mutation here invalidates it: reading one notification has to move the badge, and waiting up to
 * 30 seconds for the next poll would make the UI look broken.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiGet, apiPost, ensureCsrfCookie, type Paginated } from '../../lib/http'
import { queryKeys } from '../../lib/queryClient'
import { useToast } from '../../components/toast/ToastProvider'
import type { Notification } from '../../types/api'

export const notificationsApi = {
  list: (unreadOnly: boolean, page = 1) =>
    apiGet<Paginated<Notification>>('/notifications/', {
      unread: unreadOnly ? 'true' : undefined,
      page,
    }),

  unreadCount: () => apiGet<{ unread: number }>('/notifications/unread-count/'),

  markRead: (id: string) => apiPost<Notification>(`/notifications/${id}/read/`),

  /** Returns `{marked_read: n}` — the number of rows affected. */
  readAll: () => apiPost<{ marked_read: number }>('/notifications/read-all/'),
}

export function useNotifications(unreadOnly: boolean, page: number) {
  return useQuery({
    queryKey: queryKeys.notifications.list(unreadOnly, page),
    queryFn: () => notificationsApi.list(unreadOnly, page),
    // The badge has its own poller; re-reading the whole page on focus is unnecessary noise.
    refetchOnWindowFocus: false,
  })
}

function invalidateInbox(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: ['notifications'] })
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await ensureCsrfCookie()
      return notificationsApi.markRead(id)
    },
    onSuccess: () => invalidateInbox(queryClient),
    onError: () => {
      /* A failed read-marking is not worth interrupting the user; the badge will re-poll. */
    },
  })
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async () => {
      await ensureCsrfCookie()
      return notificationsApi.readAll()
    },
    onSuccess: (result) => {
      invalidateInbox(queryClient)
      toast.success(
        result.marked_read > 0 ? 'All caught up' : 'Nothing to mark',
        result.marked_read > 0 ? `${result.marked_read} notification(s) marked as read.` : undefined,
      )
    },
    onError: (error) => toast.error('Could not mark notifications as read', detailOf(error)),
  })
}

function detailOf(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Please try again.'
}
