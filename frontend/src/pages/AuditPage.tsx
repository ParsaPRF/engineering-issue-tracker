/**
 * Admin audit log.
 *
 * `GET /audit/` is `IsAdminUser`, so this screen is reached from an admin-only sidebar entry and its
 * own request is the real gate: a non-admin who navigates here by URL gets the API's 403 rendered as
 * an error state, which is the honest outcome (hiding the screen client-side would pretend the
 * permission question had been answered locally).
 */

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CellStack, PageHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { Pagination, Table, type Column } from '../components/ui/Table';
import { useAuditEvents } from '../features/reports/hooks';
import { useAuthContext, isAdmin } from '../features/auth/hooks/useAuthContext';
import { auditActionLabel, formatDateTime, formatRelative, metadataSummary } from '../lib/format';
import type { AuditEvent } from '../types/api';

/**
 * The action vocabulary, mirroring `apps.audit.actions.AuditAction`.
 *
 * A local list is acceptable here — unlike ticket statuses, it is only used to populate a filter
 * dropdown, and an unknown action still renders correctly through `auditActionLabel`'s fallback.
 */
const AUDIT_ACTIONS = [
  'user.registered',
  'user.logged_in',
  'user.logged_out',
  'user.activated',
  'user.deactivated',
  'user.role_changed',
  'user.profile_updated',
  'project.created',
  'project.updated',
  'project.archived',
  'project.restored',
  'membership.added',
  'membership.reactivated',
  'membership.role_changed',
  'membership.removed',
  'component.created',
  'component.updated',
  'component.deactivated',
  'ticket.created',
  'ticket.updated',
  'ticket.assigned',
  'ticket.reassigned',
  'ticket.unassigned',
  'ticket.status_changed',
  'ticket.labels_changed',
  'comment.created',
  'comment.updated',
  'comment.deleted',
  'attachment.uploaded',
  'attachment.downloaded',
  'attachment.deleted',
]

const OBJECT_TYPES = ['user', 'project', 'membership', 'component', 'ticket', 'comment', 'attachment']

export function AuditPage() {
  const { user } = useAuthContext();
  const admin = isAdmin(user);

  const [action, setAction] = useState('');
  const [objectType, setObjectType] = useState('');
  const [page, setPage] = useState(1);

  const params = useMemo(
    () => ({
      action: action || undefined,
      object_type: objectType || undefined,
      page,
      page_size: 25,
      ordering: '-created_at',
    }),
    [action, objectType, page],
  );

  // Don't fire a request that is guaranteed to 403: the screen explains the requirement instead.
  const audit = useAuditEvents(params, admin);

  const columns: Array<Column<AuditEvent>> = [
    {
      key: 'action',
      header: 'Action',
      tight: true,
      render: (event) => <Badge tone="outline">{auditActionLabel(event.action)}</Badge>,
    },
    {
      key: 'actor',
      header: 'Actor',
      render: (event) => (
        <CellStack primary={event.actor_name ?? 'System'} secondary={event.actor_email ?? undefined} />
      ),
    },
    {
      key: 'object',
      header: 'Object',
      render: (event) => (
        <CellStack
          primary={
            event.ticket_key ?? event.project_key ?? `${event.object_type} ${event.object_id.slice(0, 8)}`
          }
          secondary={event.object_type}
        />
      ),
    },
    {
      key: 'metadata',
      header: 'Details',
      render: (event) => (
        <span className="cell-stack__secondary" title={JSON.stringify(event.metadata)}>
          {metadataSummary(event.metadata)}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'When',
      tight: true,
      render: (event) => (
        <span className="cell-stack__secondary" title={formatDateTime(event.created_at)}>
          {formatRelative(event.created_at)}
        </span>
      ),
    },
  ];

  if (!admin) {
    return (
      <>
        <PageHeader title="Audit log" subtitle="Administrator access required." />
        <Card>
          <EmptyState
            title="Administrators only"
            message="The audit trail is restricted to administrators. Project activity is available to members through the dashboard and reports."
            action={
              <Link to="/reports" className="btn btn--secondary">
                Open reports
              </Link>
            }
          />
        </Card>
      </>
    );
  }

  const rows = audit.data?.results ?? [];

  return (
    <>
      <PageHeader
        title="Audit log"
        subtitle="Every recorded event, newest first. Read-only by design: history cannot be written through the API."
        actions={
          <Button variant="secondary" onClick={() => void audit.refetch()} loading={audit.isFetching}>
            Refresh
          </Button>
        }
      />

      <Card flush>
        <div className="toolbar">
          <div className="toolbar__field">
            <label className="field__label" htmlFor="audit-action">
              Action
            </label>
            <select
              id="audit-action"
              className="select"
              value={action}
              onChange={(event) => {
                setAction(event.target.value);
                setPage(1);
              }}
            >
              <option value="">All actions</option>
              {AUDIT_ACTIONS.map((value) => (
                <option key={value} value={value}>
                  {auditActionLabel(value)}
                </option>
              ))}
            </select>
          </div>
          <div className="toolbar__field">
            <label className="field__label" htmlFor="audit-object">
              Object type
            </label>
            <select
              id="audit-object"
              className="select"
              value={objectType}
              onChange={(event) => {
                setObjectType(event.target.value);
                setPage(1);
              }}
            >
              <option value="">All objects</option>
              {OBJECT_TYPES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <div className="toolbar__actions">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setAction('');
                setObjectType('');
                setPage(1);
              }}
              disabled={!action && !objectType}
            >
              Clear filters
            </Button>
          </div>
        </div>

        {audit.isLoading ? (
          <LoadingState label="Loading audit events…" />
        ) : audit.isError ? (
          <ErrorState title="Could not load the audit log" error={audit.error} onRetry={() => void audit.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No audit events match"
            message="Adjust the filters, or wait for activity in the projects you administer."
          />
        ) : (
          <>
            <Table
              columns={columns}
              rows={rows}
              rowKey={(event) => event.id}
              refreshing={audit.isFetching}
              caption="Audit events"
            />
            <Pagination
              page={audit.data?.page ?? 1}
              totalPages={audit.data?.total_pages ?? 1}
              count={audit.data?.count ?? 0}
              pageSize={audit.data?.page_size ?? 25}
              onPageChange={setPage}
            />
          </>
        )}
      </Card>
    </>
  );
}
