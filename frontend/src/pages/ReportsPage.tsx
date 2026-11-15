/**
 * Reports.
 *
 * Renders the aggregate endpoints the backend already computes — the client does no counting of its
 * own. That is deliberate: `/reports/*` scopes every number to the caller's visible projects in SQL,
 * so a chart drawn from a fetched page would be both slower and subtly wrong (it would only count
 * the rows that happen to be on that page).
 *
 * The workflow catalogue is shown here as a reference panel, because "what moves are possible, for
 * which role" is documentation that belongs next to the workload numbers rather than hidden in code.
 */

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CellStack, PageHeader, StatCard } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { MultiSelect } from '../components/ui/MultiSelect';
import { Badge, RoleBadge } from '../components/ui/Badge';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { Table, type Column } from '../components/ui/Table';
import {
  ActivityFeed,
  BreakdownBars,
  PRIORITY_BAR_TONES,
  SEVERITY_BAR_TONES,
  STATUS_BAR_TONES,
} from '../components/DomainBits';
import {
  useDashboardReport,
  useProjectOptions,
  useRecentActivity,
  useWorkloadReport,
} from '../features/reports/hooks';
import { useWorkflowCatalogue } from '../features/tickets/hooks';
import {
  PRIORITY_ORDER,
  SEVERITY_ORDER,
  STATUS_BAR_ORDER,
  percent,
  roleLabel,
  statusLabel,
} from '../lib/format';
import type { WorkloadRow } from '../types/api';

export function ReportsPage() {
  const [projectIds, setProjectIds] = useState<string[]>([]);

  const options = useProjectOptions();
  const dashboard = useDashboardReport(projectIds);
  const workload = useWorkloadReport(projectIds);
  const activity = useRecentActivity(20);
  const catalogue = useWorkflowCatalogue();

  const projectFilterOptions = useMemo(
    () =>
      (options.data?.results ?? []).map((project) => ({
        value: project.id,
        label: `${project.key} — ${project.name}`,
      })),
    [options.data],
  );

  const maxOpen = useMemo(
    () => Math.max(1, ...(workload.data?.results ?? []).map((row) => row.open_tickets)),
    [workload.data],
  );

  const workloadColumns: Array<Column<WorkloadRow>> = [
    {
      key: 'person',
      header: 'Person',
      render: (row) => <CellStack primary={row.full_name} secondary={row.email} />,
    },
    {
      key: 'open',
      header: 'Open',
      align: 'right',
      tight: true,
      render: (row) => (
        <span className="row row--nowrap" style={{ justifyContent: 'flex-end' }}>
          <span className="breakdown__track" style={{ width: 80 }}>
            <span
              className="breakdown__fill breakdown__fill--accent"
              style={{ width: `${percent(row.open_tickets, maxOpen)}%` }}
            />
          </span>
          <strong>{row.open_tickets}</strong>
        </span>
      ),
    },
    { key: 'total', header: 'Total', align: 'right', tight: true, render: (row) => row.total_tickets },
    {
      key: 'blocked',
      header: 'Blocked',
      align: 'right',
      tight: true,
      render: (row) =>
        row.blocked_tickets > 0 ? <Badge tone="danger">{row.blocked_tickets}</Badge> : <span>0</span>,
    },
    {
      key: 'tickets',
      header: '',
      align: 'right',
      tight: true,
      render: (row) => (
        <Link to={`/tickets?assignee=${row.user_id}&open_only=true`} className="btn btn--ghost btn--sm">
          View
        </Link>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Reports"
        subtitle="Workload, distributions and recent activity across the projects you belong to."
        actions={
          <Button variant="secondary" onClick={() => void dashboard.refetch()} loading={dashboard.isFetching}>
            Refresh
          </Button>
        }
      />

      <div className="stack">
        {projectFilterOptions.length > 1 ? (
          <div style={{ maxWidth: 380 }}>
            <MultiSelect
              label="Scope"
              options={projectFilterOptions}
              values={projectIds}
              onChange={setProjectIds}
              placeholder="All visible projects"
            />
          </div>
        ) : null}

        {/* ---- Headline numbers ------------------------------------------ */}
        {dashboard.isLoading ? (
          <LoadingState label="Loading report…" />
        ) : dashboard.isError ? (
          <Card>
            <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />
          </Card>
        ) : dashboard.data ? (
          <>
            <div className="stat-grid">
              <StatCard label="Total tickets" value={dashboard.data.totals.total_tickets} accent="accent" />
              <StatCard label="Open" value={dashboard.data.totals.open_tickets} accent="warning" />
              <StatCard
                label="Unassigned open"
                value={dashboard.data.totals.unassigned_tickets}
                meta="Nobody owns these yet"
              />
              <StatCard label="Blocked" value={dashboard.data.totals.blocked_tickets} accent="danger" />
              <StatCard label="Resolved" value={dashboard.data.totals.resolved_tickets} accent="success" />
              <StatCard
                label="Projects in scope"
                value={dashboard.data.project_count}
                meta={`${dashboard.data.by_project.length} with tickets`}
              />
            </div>

            <div className="grid grid--3">
              <Card title="Priority distribution">
                <BreakdownBars
                  title="By priority"
                  data={dashboard.data.by_priority}
                  order={[...PRIORITY_ORDER]}
                  toneByValue={PRIORITY_BAR_TONES}
                />
              </Card>
              <Card title="Severity distribution">
                <BreakdownBars
                  title="By severity"
                  data={dashboard.data.by_severity}
                  order={[...SEVERITY_ORDER]}
                  toneByValue={SEVERITY_BAR_TONES}
                />
              </Card>
              <Card title="Status distribution">
                <BreakdownBars
                  title="By status"
                  data={dashboard.data.by_status}
                  order={STATUS_BAR_ORDER}
                  toneByValue={STATUS_BAR_TONES}
                />
              </Card>
            </div>

            <Card title="By ticket type" subtitle="What kind of work is arriving">
              <BreakdownBars title="By type" data={dashboard.data.by_type} />
            </Card>
          </>
        ) : null}

        {/* ---- Workload + activity --------------------------------------- */}
        <div className="grid grid--2">
          <Card
            title="Workload"
            subtitle="Open tickets per engineer, including people with none"
            flush
          >
            {workload.isLoading ? (
              <LoadingState />
            ) : workload.isError ? (
              <ErrorState error={workload.error} onRetry={() => void workload.refetch()} inline />
            ) : (workload.data?.results.length ?? 0) === 0 ? (
              <EmptyState
                inline
                title="No engineers in scope"
                message="Workload lists engineers and managers who are members of the projects you can see."
              />
            ) : (
              <Table
                columns={workloadColumns}
                rows={workload.data?.results ?? []}
                rowKey={(row) => row.user_id}
                caption="Engineer workload"
              />
            )}
          </Card>

          <Card title="Recent activity" subtitle="The last 20 audit events you can see" flush>
            {activity.isLoading ? (
              <LoadingState />
            ) : activity.isError ? (
              <ErrorState error={activity.error} onRetry={() => void activity.refetch()} inline />
            ) : (activity.data?.results.length ?? 0) === 0 ? (
              <EmptyState inline title="No activity" message="Nothing has happened in your projects yet." />
            ) : (
              <ActivityFeed events={activity.data?.results ?? []} />
            )}
          </Card>
        </div>

        {/* ---- Per-project table ----------------------------------------- */}
        {dashboard.data ? (
          <Card title="Tickets by project" flush>
            <Table
              columns={[
                {
                  key: 'project',
                  header: 'Project',
                  render: (row) => (
                    <CellStack
                      primary={<Link to={`/projects/${row.project_id}`}>{row.project_key}</Link>}
                      secondary={row.project_name}
                    />
                  ),
                },
                { key: 'total', header: 'Tickets', align: 'right', tight: true, render: (row) => row.total_tickets },
                { key: 'open', header: 'Open', align: 'right', tight: true, render: (row) => row.open_tickets },
                {
                  key: 'share',
                  header: 'Share of open',
                  align: 'right',
                  tight: true,
                  render: (row) => `${percent(row.open_tickets, dashboard.data?.totals.open_tickets ?? 0)}%`,
                },
              ]}
              rows={dashboard.data.by_project}
              rowKey={(row) => row.project_id}
              caption="Tickets by project"
            />
          </Card>
        ) : null}

        {/* ---- Workflow reference ---------------------------------------- */}
        <Card
          title="Workflow reference"
          subtitle="Every legal status change, read from the backend's own state machine"
        >
          {catalogue.isLoading ? (
            <LoadingState />
          ) : catalogue.isError ? (
            <ErrorState error={catalogue.error} onRetry={() => void catalogue.refetch()} inline />
          ) : (
            <div className="stack">
              <p className="field__hint">
                {catalogue.data?.declared_move_count} declared move(s) across{' '}
                {catalogue.data?.statuses.length ?? 0} status(es). The ticket screen renders its buttons
                from this catalogue, so the UI cannot offer a move the backend would reject.
              </p>
              <Table
                columns={[
                  {
                    key: 'move',
                    header: 'Move',
                    render: (rule) => (
                      <span className="row row--nowrap">
                        <Badge tone="neutral">{statusLabel(rule.from_status)}</Badge>
                        <span className="workflow-arrow">→</span>
                        <Badge tone="accent">{statusLabel(rule.to_status)}</Badge>
                      </span>
                    ),
                  },
                  {
                    key: 'roles',
                    header: 'Allowed roles',
                    render: (rule) => (
                      <span className="row">
                        {rule.allowed_project_roles.map((role) => (
                          <RoleBadge key={role} role={role} label={roleLabel(role)} />
                        ))}
                        {rule.allow_assignee ? <Badge tone="outline">or the assignee</Badge> : null}
                      </span>
                    ),
                  },
                  {
                    key: 'requirements',
                    header: 'Requires',
                    render: (rule) => (
                      <span className="row">
                        {rule.requires_comment ? <Badge tone="warning">comment</Badge> : null}
                        {rule.requires_assignee ? <Badge tone="warning">assignee</Badge> : null}
                        {!rule.requires_comment && !rule.requires_assignee ? (
                          <span className="cell-stack__secondary">nothing</span>
                        ) : null}
                      </span>
                    ),
                  },
                ]}
                rows={catalogue.data?.transitions ?? []}
                rowKey={(rule) => `${rule.from_status}-${rule.to_status}`}
              />
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
