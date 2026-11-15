/**
 * Dashboard.
 *
 * Assembled from `/reports/dashboard/` (totals and breakdowns), `/reports/my-workload/` (the
 * caller's own queue) and `/reports/recent-activity/` (the audit feed, scoped to visible projects).
 *
 * All three panels carry their own loading, empty and error state: a broken activity feed must not
 * blank the totals, so the sections are independent rather than one big `isLoading` gate.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader, Card, StatCard, CellStack } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { MultiSelect } from '../components/ui/MultiSelect'
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States'
import { Table, type Column } from '../components/ui/Table'
import {
  ActivityFeed,
  BreakdownBars,
  PRIORITY_BAR_TONES,
  SEVERITY_BAR_TONES,
  STATUS_BAR_TONES,
  StatusDistribution,
} from '../components/DomainBits'
import { useAuthContext } from '../features/auth/hooks/useAuthContext'
import { useDashboardReport, useMyWorkload, useProjectOptions, useRecentActivity } from '../features/reports/hooks'
import { PRIORITY_ORDER, SEVERITY_ORDER, STATUS_BAR_ORDER, statusLabel } from '../lib/format'
import type { ProjectBreakdownRow } from '../types/api'

export function DashboardPage() {
  const { user } = useAuthContext()
  const [projectIds, setProjectIds] = useState<string[]>([])

  const options = useProjectOptions()
  const dashboard = useDashboardReport(projectIds)
  const workload = useMyWorkload()
  const activity = useRecentActivity(12)

  const projectFilterOptions = useMemo(
    () => (options.data?.results ?? []).map((project) => ({ value: project.id, label: `${project.key} — ${project.name}` })),
    [options.data],
  )

  const projectColumns: Array<Column<ProjectBreakdownRow>> = [
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
      key: 'link',
      header: '',
      align: 'right',
      tight: true,
      render: (row) => (
        <Link to={`/tickets?project=${row.project_id}`} className="btn btn--ghost btn--sm">
          View tickets
        </Link>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title={`Welcome back${user ? `, ${user.full_name.split(' ')[0]}` : ''}`}
        subtitle="Ticket health across the projects you belong to."
        actions={
          <>
            <Button variant="secondary" onClick={() => void dashboard.refetch()}>
              Refresh
            </Button>
            <Link to="/tickets/new" className="btn btn--primary">
              New ticket
            </Link>
          </>
        }
      />

      {options.data && options.data.results.length > 1 ? (
        <div style={{ marginBottom: 'var(--space-4)', maxWidth: 340 }}>
          <MultiSelect
            label="Filter by project"
            options={projectFilterOptions}
            values={projectIds}
            onChange={setProjectIds}
            placeholder="All visible projects"
          />
        </div>
      ) : null}

      <div className="stack">
        {/* ---- Totals ---------------------------------------------------- */}
        {dashboard.isLoading ? (
          <LoadingState label="Loading ticket totals…" />
        ) : dashboard.isError ? (
          <Card>
            <ErrorState
              title="Could not load the dashboard"
              error={dashboard.error}
              onRetry={() => void dashboard.refetch()}
            />
          </Card>
        ) : dashboard.data ? (
          <div className="stat-grid">
            <StatCard
              label="Total tickets"
              value={dashboard.data.totals.total_tickets}
              meta={`${dashboard.data.project_count} project(s) visible`}
              accent="accent"
            />
            <StatCard
              label="Open"
              value={dashboard.data.totals.open_tickets}
              meta={`${dashboard.data.totals.unassigned_tickets} unassigned`}
              accent="warning"
            />
            <StatCard
              label="Resolved"
              value={dashboard.data.totals.resolved_tickets}
              meta={`${dashboard.data.totals.closed_tickets} closed`}
              accent="success"
            />
            <StatCard
              label="Blocked"
              value={dashboard.data.totals.blocked_tickets}
              meta="Needs attention"
              accent="danger"
            />
          </div>
        ) : null}

        {/* ---- Breakdowns ------------------------------------------------ */}
        {dashboard.data ? (
          <div className="grid grid--3">
            <Card title="By priority" subtitle="How soon the work is needed">
              <BreakdownBars
                title="Tickets by priority"
                data={dashboard.data.by_priority}
                order={[...PRIORITY_ORDER]}
                toneByValue={PRIORITY_BAR_TONES}
              />
            </Card>
            <Card title="By severity" subtitle="How serious the technical impact is">
              <BreakdownBars
                title="Tickets by severity"
                data={dashboard.data.by_severity}
                order={[...SEVERITY_ORDER]}
                toneByValue={SEVERITY_BAR_TONES}
              />
            </Card>
            <Card title="By status" subtitle={`${dashboard.data.totals.total_tickets} ticket(s) in scope`}>
              <StatusDistribution data={dashboard.data.by_status} order={STATUS_BAR_ORDER} />
            </Card>
          </div>
        ) : null}

        {/* ---- Per-project table + side panels --------------------------- */}
        <div className="grid grid--sidebar">
          <div className="stack">
            <Card
              title="Tickets by project"
              subtitle="Where the work currently sits"
              flush
              actions={
                <Link to="/projects" className="btn btn--ghost btn--sm">
                  All projects
                </Link>
              }
            >
              {dashboard.isLoading ? (
                <LoadingState />
              ) : dashboard.isError ? (
                <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} inline />
              ) : (dashboard.data?.by_project.length ?? 0) === 0 ? (
                <EmptyState
                  inline
                  title="No tickets yet"
                  message="Projects appear here as soon as they contain tickets. Create one to get started."
                  action={
                    <Link to="/tickets/new" className="btn btn--primary btn--sm">
                      New ticket
                    </Link>
                  }
                />
              ) : (
                <Table
                  columns={projectColumns}
                  rows={dashboard.data?.by_project ?? []}
                  rowKey={(row) => row.project_id}
                  caption="Ticket counts per project"
                />
              )}
            </Card>

            <Card
              title="Recent activity"
              subtitle="Audit events from projects you belong to"
              flush
            >
              {activity.isLoading ? (
                <LoadingState />
              ) : activity.isError ? (
                <ErrorState error={activity.error} onRetry={() => void activity.refetch()} inline />
              ) : (activity.data?.results.length ?? 0) === 0 ? (
                <EmptyState
                  inline
                  title="No activity recorded"
                  message="Ticket changes, comments and status moves will show up here."
                />
              ) : (
                <ActivityFeed events={activity.data?.results ?? []} />
              )}
            </Card>
          </div>

          <aside className="detail-aside detail-aside--sticky">
            <Card title="My workload" subtitle="Assigned to you">
              {workload.isLoading ? (
                <LoadingState />
              ) : workload.isError ? (
                <ErrorState error={workload.error} onRetry={() => void workload.refetch()} inline />
              ) : workload.data ? (
                <div className="stack">
                  <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
                    <StatCard label="Open" value={workload.data.open_tickets} />
                    <StatCard label="Total" value={workload.data.total_tickets} />
                  </div>
                  <BreakdownBars
                    title="My tickets by status"
                    data={workload.data.by_status}
                    order={STATUS_BAR_ORDER}
                    toneByValue={STATUS_BAR_TONES}
                  />
                  <Link to="/my-assignments" className="btn btn--secondary btn--sm btn--block">
                    Open my assignments
                  </Link>
                </div>
              ) : null}
            </Card>

            <Card title="Quick links">
              <div className="stack stack--tight">
                <Link to="/tickets?open_only=true&ordering=-priority" className="btn btn--ghost btn--sm btn--block">
                  Highest-priority open tickets
                </Link>
                <Link to="/tickets?overdue=true" className="btn btn--ghost btn--sm btn--block">
                  Overdue tickets
                </Link>
                <Link to="/tickets?unassigned=true&open_only=true" className="btn btn--ghost btn--sm btn--block">
                  Unassigned open tickets
                </Link>
                <Link to="/reports" className="btn btn--ghost btn--sm btn--block">
                  Team workload report
                </Link>
              </div>
            </Card>

            <Card title="Statuses" subtitle="The lifecycle this tracker uses">
              <ul className="stack stack--tight">
                {STATUS_BAR_ORDER.map((status) => (
                  <li key={status} className="row row--between">
                    <span className="field__hint">{statusLabel(status)}</span>
                    <span className="cell-stack__secondary">{dashboard.data?.by_status[status] ?? 0}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </aside>
        </div>
      </div>
    </>
  )
}
