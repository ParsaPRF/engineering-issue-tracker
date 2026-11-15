/**
 * My assignments.
 *
 * `/tickets/my-assignments/` is a dedicated endpoint rather than a filter on `/tickets/`, because
 * "the caller's own open queue" is the single most-requested list and deserves its own query. The
 * `include_done` switch is passed through verbatim (`?include_done=true`), not re-derived here.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, PageHeader, StatCard } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { Pagination, Table, type Column } from '../components/ui/Table';
import { AssigneeCell, DueDateCell, TicketBadges, TicketLinkCell } from '../components/DomainBits';
import { useMyAssignments } from '../features/tickets/hooks';
import { useMyWorkload } from '../features/reports/hooks';
import { STATUS_BAR_ORDER, formatRelative, statusLabel } from '../lib/format';
import type { TicketListItem } from '../types/api';

export function MyAssignmentsPage() {
  const [includeDone, setIncludeDone] = useState(false);
  const [page, setPage] = useState(1);

  const assignments = useMyAssignments(includeDone, page);
  const workload = useMyWorkload();
  const rows = assignments.data?.results ?? [];

  const columns: Array<Column<TicketListItem>> = [
    { key: 'key', header: 'Key', render: (ticket) => <TicketLinkCell ticket={ticket} /> },
    {
      key: 'project',
      header: 'Project',
      tight: true,
      render: (ticket) => <Link to={`/projects/${ticket.project.id}`}>{ticket.project.key}</Link>,
    },
    {
      key: 'state',
      header: 'State',
      tight: true,
      render: (ticket) => (
        <TicketBadges status={ticket.status} priority={ticket.priority} severity={ticket.severity} />
      ),
    },
    { key: 'assignee', header: 'Assignee', tight: true, render: (ticket) => <AssigneeCell ticket={ticket} /> },
    { key: 'due_date', header: 'Due', tight: true, render: (ticket) => <DueDateCell ticket={ticket} /> },
    {
      key: 'updated_at',
      header: 'Updated',
      tight: true,
      render: (ticket) => <span className="cell-stack__secondary">{formatRelative(ticket.updated_at)}</span>,
    },
  ];

  return (
    <>
      <PageHeader
        title="My assignments"
        subtitle="Tickets currently assigned to you."
        actions={
          <>
            <Button variant="secondary" onClick={() => void assignments.refetch()} loading={assignments.isFetching}>
              Refresh
            </Button>
            <Link to="/tickets/new" className="btn btn--primary">
              New ticket
            </Link>
          </>
        }
      />

      <div className="stack">
        <div className="stat-grid">
          <StatCard
            label="Open"
            value={workload.data?.open_tickets ?? '—'}
            meta="Not resolved or closed"
            accent="warning"
          />
          <StatCard label="Total assigned" value={workload.data?.total_tickets ?? '—'} meta="Ever assigned to you" />
          <StatCard
            label="On this page"
            value={rows.length}
            meta={`${assignments.data?.count ?? 0} in this view`}
            accent="accent"
          />
        </div>

        {workload.data ? (
          <Card title="My tickets by status" subtitle="Including finished work">
            <div className="breakdown">
              {STATUS_BAR_ORDER.filter((status) => (workload.data?.by_status[status] ?? 0) > 0).map((status) => {
                const value = workload.data?.by_status[status] ?? 0;
                const total = workload.data?.total_tickets ?? 0;
                return (
                  <div className="breakdown__row" key={status}>
                    <span className="breakdown__label">{statusLabel(status)}</span>
                    <span className="breakdown__track">
                      <span
                        className="breakdown__fill breakdown__fill--accent"
                        style={{ width: `${total > 0 ? (value / total) * 100 : 0}%` }}
                      />
                    </span>
                    <span className="breakdown__value">{value}</span>
                  </div>
                );
              })}
              {STATUS_BAR_ORDER.every((status) => (workload.data?.by_status[status] ?? 0) === 0) ? (
                <p className="field__hint">Nothing is assigned to you yet.</p>
              ) : null}
            </div>
          </Card>
        ) : null}

        <Card flush>
          <div className="toolbar">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={includeDone}
                onChange={(event) => {
                  setIncludeDone(event.target.checked);
                  setPage(1);
                }}
              />
              <span>Include resolved and closed tickets</span>
            </label>
            <div className="toolbar__actions">
              <Link to="/tickets?assignee=me" className="btn btn--ghost btn--sm">
                Open in ticket list
              </Link>
            </div>
          </div>

          {assignments.isLoading ? (
            <LoadingState label="Loading your assignments…" />
          ) : assignments.isError ? (
            <ErrorState
              title="Could not load your assignments"
              error={assignments.error}
              onRetry={() => void assignments.refetch()}
            />
          ) : rows.length === 0 ? (
            <EmptyState
              title={includeDone ? 'Nothing is assigned to you' : 'Your queue is clear'}
              message={
                includeDone
                  ? 'No tickets have ever been assigned to you in the projects you belong to.'
                  : 'No open tickets are assigned to you. Switch the toggle to see finished work.'
              }
              action={
                includeDone ? null : (
                  <Button variant="secondary" onClick={() => setIncludeDone(true)}>
                    Include finished tickets
                  </Button>
                )
              }
            />
          ) : (
            <>
              <Table
                columns={columns}
                rows={rows}
                rowKey={(ticket) => ticket.id}
                refreshing={assignments.isFetching}
                caption="Tickets assigned to you"
              />
              <Pagination
                page={assignments.data?.page ?? 1}
                totalPages={assignments.data?.total_pages ?? 1}
                count={assignments.data?.count ?? 0}
                pageSize={assignments.data?.page_size ?? 25}
                onPageChange={setPage}
              />
            </>
          )}
        </Card>
      </div>
    </>
  );
}
