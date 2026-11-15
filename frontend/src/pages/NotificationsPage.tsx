/**
 * Notifications inbox.
 *
 * `unread=true` is the server-side filter (`inbox(unread_only=...)`), not a client filter over a
 * fetched page — filtering client-side would show "no unread" whenever the unread ones happened to
 * fall on another page.
 *
 * Marking one as read invalidates the whole notification key space, which includes the topbar badge
 * query, so the count moves immediately rather than at the next 30-second poll.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, PageHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { Pagination } from '../components/ui/Table';
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications } from '../features/notifications/hooks';
import { useUnreadNotificationCount } from '../features/auth/hooks';
import { formatDateTime, formatRelative, humanise } from '../lib/format';
import type { Notification } from '../types/api';

export function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [page, setPage] = useState(1);

  const notifications = useNotifications(unreadOnly, page);
  const unreadCount = useUnreadNotificationCount(true);
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const rows = notifications.data?.results ?? [];
  const unread = unreadCount.data?.unread ?? 0;

  return (
    <>
      <PageHeader
        title="Notifications"
        subtitle={unread > 0 ? `${unread} unread notification(s).` : 'You are all caught up.'}
        actions={
          <>
            <Button variant="secondary" onClick={() => void notifications.refetch()} loading={notifications.isFetching}>
              Refresh
            </Button>
            <Button
              variant="primary"
              onClick={() => markAllRead.mutate()}
              loading={markAllRead.isPending}
              disabled={unread === 0}
            >
              Mark all as read
            </Button>
          </>
        }
      />

      <Card flush>
        <div className="toolbar">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(event) => {
                setUnreadOnly(event.target.checked);
                setPage(1);
              }}
            />
            <span>Unread only</span>
          </label>
          {unread > 0 ? (
            <span className="field__hint">
              {unread} unread. The badge in the top bar updates as you read them.
            </span>
          ) : null}
        </div>

        {notifications.isLoading ? (
          <LoadingState label="Loading notifications…" />
        ) : notifications.isError ? (
          <ErrorState
            title="Could not load notifications"
            error={notifications.error}
            onRetry={() => void notifications.refetch()}
          />
        ) : rows.length === 0 ? (
          <EmptyState
            title={unreadOnly ? 'No unread notifications' : 'No notifications yet'}
            message={
              unreadOnly
                ? 'Everything has been read. Untick the filter to see your history.'
                : 'You will be told here when a ticket you care about is assigned, commented on or moved.'
            }
            action={
              unreadOnly ? (
                <Button variant="secondary" onClick={() => setUnreadOnly(false)}>
                  Show all notifications
                </Button>
              ) : null
            }
          />
        ) : (
          <>
            <ul className="notification-list">
              {rows.map((notification) => (
                <NotificationRow
                  key={notification.id}
                  notification={notification}
                  onMarkRead={() => markRead.mutate(notification.id)}
                  marking={markRead.isPending}
                />
              ))}
            </ul>
            <Pagination
              page={notifications.data?.page ?? 1}
              totalPages={notifications.data?.total_pages ?? 1}
              count={notifications.data?.count ?? 0}
              pageSize={notifications.data?.page_size ?? 25}
              onPageChange={setPage}
            />
          </>
        )}
      </Card>
    </>
  );
}

function NotificationRow({
  notification,
  onMarkRead,
  marking,
}: {
  notification: Notification;
  onMarkRead: () => void;
  marking: boolean;
}) {
  return (
    <li className={`notification${notification.is_read ? '' : ' notification--unread'}`}>
      <span
        className={`notification__dot${notification.is_read ? ' notification__dot--read' : ''}`}
        aria-hidden="true"
      />
      <div className="notification__main">
        <p className="notification__title">{notification.title}</p>
        {notification.body ? <p className="notification__body">{notification.body}</p> : null}
        <div className="notification__meta">
          <span className="badge badge--outline">{humanise(notification.event_type.split('.')[1] ?? notification.event_type)}</span>
          {notification.actor_name ? <span>{notification.actor_name}</span> : <span>System</span>}
          {notification.ticket_key ? (
            <Link to={`/tickets?search=${encodeURIComponent(notification.ticket_key)}`}>
              {notification.ticket_key}
            </Link>
          ) : null}
          {notification.project_key ? <span>{notification.project_key}</span> : null}
          <span title={formatDateTime(notification.created_at)}>{formatRelative(notification.created_at)}</span>
        </div>
      </div>
      {!notification.is_read ? (
        <Button size="sm" variant="ghost" onClick={onMarkRead} loading={marking}>
          Mark read
        </Button>
      ) : null}
    </li>
  );
}
