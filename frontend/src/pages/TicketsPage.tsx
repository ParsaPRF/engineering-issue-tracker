/**
 * Ticket list.
 *
 * Every piece of list state — filters, sort, page — lives in the query string, so the screen is
 * shareable and the dashboard's quick links arrive pre-filtered. The table itself does no filtering
 * or sorting: `?ordering=` is handed to the API, which ranks `priority` and `severity` semantically
 * (a naive client sort would put `CRITICAL` before `LOW` alphabetically and call it "most urgent").
 */

import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Card, PageHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { Pagination, Table, type Column } from '../components/ui/Table';
import { TicketFilterBar } from '../components/TicketFilterBar';
import { AssigneeCell, DueDateCell, TicketBadges, TicketLinkCell } from '../components/DomainBits';
import { useProjectMembers, useProjectComponents, useProjects } from '../features/projects/hooks';
import { useTickets, useProjectLabels } from '../features/tickets/hooks';
import { useTicketFilters } from '../hooks/useTicketFilters';
import { formatRelative } from '../lib/format';
import type { TicketListItem } from '../types/api';

/** The page size the list requests. The API caps it at 100. */
const PAGE_SIZE = 25;

export function TicketsPage() {
  const filters = useTicketFilters();
  const projects = useProjects({ page_size: 100 });

  // Assignee / component / label filter options come from the selected project's own data.
  const members = useProjectMembers(filters.project || undefined);
  const components = useProjectComponents(filters.project || undefined);
  const labels = useProjectLabels(filters.project || undefined);

  const params = useMemo(
    () => ({
      project: filters.project || undefined,
      status: filters.status.length > 0 ? filters.status : undefined,
      priority: filters.priority.length > 0 ? filters.priority : undefined,
      severity: filters.severity.length > 0 ? filters.severity : undefined,
      type: filters.type.length > 0 ? filters.type : undefined,
      assignee: filters.assignee || undefined,
      component: filters.component || undefined,
      label: filters.label || undefined,
      overdue: filters.overdue || undefined,
      unassigned: filters.unassigned || undefined,
      open_only: filters.open_only || undefined,
      search: filters.search || undefined,
      ordering: filters.ordering,
      page: filters.page,
      page_size: PAGE_SIZE,
    }),
    [filters],
  );

  const tickets = useTickets(params);

  const columns: Array<Column<TicketListItem>> = [
    { key: 'key', header: 'Key', tight: true, render: (ticket) => <TicketLinkCell ticket={ticket} /> },
    {
      key: 'project',
      header: 'Project',
      tight: true,
      render: (ticket) => (
        <Link to={`/projects/${ticket.project.id}`} title={ticket.project.name}>
          {ticket.project.key}
        </Link>
      ),
    },
    {
      key: 'badges',
      header: 'State',
      tight: true,
      render: (ticket) => (
        <TicketBadges status={ticket.status} priority={ticket.priority} severity={ticket.severity} />
      ),
    },
    {
      key: 'type',
      header: 'Type',
      tight: true,
      render: (ticket) => (
        <Link to={`/tickets?type=${ticket.type}`} className="cell-stack__secondary">
          {ticket.type.replace(/_/g, ' ')}
        </Link>
      ),
    },
    { key: 'assignee', header: 'Assignee', render: (ticket) => <AssigneeCell ticket={ticket} /> },
    { key: 'due_date', header: 'Due', tight: true, render: (ticket) => <DueDateCell ticket={ticket} /> },
    {
      key: 'updated_at',
      header: 'Updated',
      tight: true,
      render: (ticket) => (
        <span className="cell-stack__secondary" title={ticket.updated_at}>
          {formatRelative(ticket.updated_at)}
        </span>
      ),
    },
  ];

  const projectOptions = projects.data?.results ?? [];
  const hasRows = (tickets.data?.results.length ?? 0) > 0;

  return (
    <>
      <PageHeader
        title="Tickets"
        subtitle={
          tickets.data
            ? `${tickets.data.count} ticket(s) match the current filters.`
            : 'Filter, sort and open any ticket you have access to.'
        }
        actions={
          <>
            <Button variant="secondary" onClick={() => void tickets.refetch()} loading={tickets.isFetching}>
              Refresh
            </Button>
            <Link to="/tickets/new" className="btn btn--primary">
              New ticket
            </Link>
          </>
        }
      />

      <Card flush>
        <div className="toolbar">
          <div className="toolbar__field" style={{ flex: '0 1 220px' }}>
            <label className="field__label" htmlFor="ticket-project-filter">
              Project
            </label>
            <select
              id="ticket-project-filter"
              className="select"
              value={filters.project}
              onChange={(event) => filters.setFilter('project', event.target.value)}
            >
              <option value="">All projects</option>
              {projectOptions.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.key} — {project.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <TicketFilterBar
          filters={filters}
          onChange={filters.setFilter}
          onReset={filters.reset}
          members={filters.project ? (members.data ?? []) : []}
          components={filters.project ? (components.data ?? []) : []}
          labels={filters.project ? (labels.data?.results ?? []) : []}
        />

        {tickets.isLoading ? (
          <LoadingState label="Loading tickets…" />
        ) : tickets.isError ? (
          <ErrorState
            title="Could not load tickets"
            error={tickets.error}
            onRetry={() => void tickets.refetch()}
          />
        ) : !hasRows ? (
          <EmptyState
            title="No tickets match these filters"
            message={
              filters.status.length > 0 || filters.search || filters.overdue || filters.unassigned
                ? 'Try clearing a filter, or search for a different key.'
                : 'Nothing has been reported yet. Create the first ticket to get started.'
            }
            action={
              <>
                <Button variant="secondary" onClick={filters.reset}>
                  Clear filters
                </Button>
                <Link to="/tickets/new" className="btn btn--primary">
                  New ticket
                </Link>
              </>
            }
          />
        ) : (
          <>
            <Table
              columns={columns}
              rows={tickets.data?.results ?? []}
              rowKey={(ticket) => ticket.id}
              refreshing={tickets.isFetching}
              ordering={{
                current: filters.ordering,
                onChange: (field) => {
                  // Clicking the active column flips the direction, as a sort header should.
                  const isActive = filters.ordering.replace('-', '') === field
                  const descending = filters.ordering.startsWith('-')
                  filters.setFilter('ordering', isActive && !descending ? `-${field}` : field)
                },
                sortable: [
                  'key',
                  'status',
                  'priority',
                  'severity',
                  'due_date',
                  'updated_at',
                  'created_at',
                ],
              }}
              caption="Tickets"
            />
            <Pagination
              page={tickets.data?.page ?? 1}
              totalPages={tickets.data?.total_pages ?? 1}
              count={tickets.data?.count ?? 0}
              pageSize={tickets.data?.page_size ?? PAGE_SIZE}
              onPageChange={filters.setPage}
            />
          </>
        )}
      </Card>
    </>
  );
}
