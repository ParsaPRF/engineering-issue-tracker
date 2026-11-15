/**
 * Team management.
 *
 * Two related but distinct jobs, on two tabs:
 *
 * * **Project teams** — who is on a given project and in what *project* role (MANAGER / ENGINEER /
 *   REPORTER). Any member can read this list; only managers can change it.
 * * **System users** — every account and its *system* role (ADMIN / PROJECT_MANAGER / ENGINEER /
 *   REPORTER), plus activation. Admin only, because that is what `IsAdmin` on `/auth/users/` says.
 *
 * The two role vocabularies are deliberately not merged in the UI either: they answer different
 * questions, and the effective permission is the combination of both.
 */

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CellStack, PageHeader, StatCard, Tabs } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge, RoleBadge } from '../components/ui/Badge';
import { Input, Select } from '../components/ui/Field';
import { ConfirmDialog } from '../components/ui/Modal';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { Pagination, Table, type Column } from '../components/ui/Table';
import { Avatar } from '../components/ui/Card';
import { useAuthContext, isAdmin } from '../features/auth/hooks/useAuthContext';
import { useChangeUserRole, useSetUserActive, useAdminUsers } from '../features/auth/hooks';
import { useProjectMembers, useProjects } from '../features/projects/hooks';
import { formatDate, formatRelative, roleLabel } from '../lib/format';
import type { AdminUser, ProjectMembership, SystemRole } from '../types/api';

import { SYSTEM_ROLES } from '../types/api';

type TabId = 'project' | 'users';

export function TeamPage() {
  const { user } = useAuthContext();
  const [tab, setTab] = useState<TabId>('project');

  const admin = isAdmin(user);

  return (
    <>
      <PageHeader
        title="Team"
        subtitle="Project membership and, for administrators, system-wide accounts."
      />

      <Card
        flush
        title={
          <Tabs
            tabs={[
              { id: 'project', label: 'Project teams' },
              { id: 'users', label: 'System users' },
            ]}
            active={tab}
            onChange={(id) => setTab(id as TabId)}
          />
        }
      >
        {tab === 'project' ? <ProjectTeamsTab /> : null}
        {tab === 'users' ? (
          admin ? (
            <SystemUsersTab />
          ) : (
            <EmptyState
              title="Administrators only"
              message="System roles and account activation are managed by administrators. You can still see each project's team on the other tab."
            />
          )
        ) : null}
      </Card>
    </>
  );
}

/* ==========================================================================
   Project teams
   ========================================================================== */

function ProjectTeamsTab() {
  const { user } = useAuthContext();
  const admin = isAdmin(user);
  const projects = useProjects({ page_size: 100, ordering: 'name' });
  const [projectId, setProjectId] = useState('');

  const projectOptions = projects.data?.results ?? [];
  // Default to the first project once the list arrives, so the tab is never blank for no reason.
  const effectiveProjectId = projectId || projectOptions[0]?.id || '';
  const members = useProjectMembers(effectiveProjectId || undefined);

  const roleCounts = useMemo(() => {
    const rows = members.data ?? [];
    return {
      total: rows.filter((row) => row.is_active).length,
      managers: rows.filter((row) => row.is_active && row.role === 'MANAGER').length,
      engineers: rows.filter((row) => row.is_active && row.role === 'ENGINEER').length,
      reporters: rows.filter((row) => row.is_active && row.role === 'REPORTER').length,
    };
  }, [members.data]);

  const columns: Array<Column<ProjectMembership>> = [
    {
      key: 'person',
      header: 'Person',
      render: (member) => (
        <span className="row row--nowrap">
          <Avatar name={member.user_name} size="sm" />
          <CellStack primary={member.user_name} secondary={member.user_email} />
        </span>
      ),
    },
    {
      key: 'role',
      header: 'Project role',
      tight: true,
      render: (member) => <Badge tone={member.role === 'MANAGER' ? 'accent' : 'neutral'}>{roleLabel(member.role)}</Badge>,
    },
    {
      key: 'system_role',
      header: 'System role',
      tight: true,
      render: (member) => <RoleBadge role={member.user.system_role} label={roleLabel(member.user.system_role)} />,
    },
    {
      key: 'active',
      header: 'Status',
      tight: true,
      render: (member) =>
        member.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="outline">Inactive</Badge>,
    },
    {
      key: 'joined',
      header: 'Joined',
      tight: true,
      render: (member) => <span className="cell-stack__secondary">{formatDate(member.joined_at)}</span>,
    },
  ];

  if (projects.isLoading) return <LoadingState label="Loading projects…" />;
  if (projects.isError) {
    return <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />;
  }
  if (projectOptions.length === 0) {
    return (
      <EmptyState
        title="No projects visible"
        message="You are not a member of any project yet, so there is no team to show."
      />
    );
  }

  return (
    <>
      <div className="toolbar">
        <div className="toolbar__field" style={{ flex: '0 1 280px' }}>
          <label className="field__label" htmlFor="team-project">
            Project
          </label>
          <select
            id="team-project"
            className="select"
            value={effectiveProjectId}
            onChange={(event) => setProjectId(event.target.value)}
          >
            {projectOptions.map((project) => (
              <option key={project.id} value={project.id}>
                {project.key} — {project.name}
              </option>
            ))}
          </select>
        </div>
        <div className="toolbar__actions">
          <Link to={`/projects/${effectiveProjectId}?tab=members`} className="btn btn--secondary btn--sm">
            Manage membership
          </Link>
        </div>
      </div>

      <div className="card__body">
        <div className="stat-grid">
          <StatCard label="Members" value={roleCounts.total} accent="accent" />
          <StatCard label="Managers" value={roleCounts.managers} meta="Can administer the project" />
          <StatCard label="Engineers" value={roleCounts.engineers} meta="Can be assigned tickets" />
          <StatCard label="Reporters" value={roleCounts.reporters} meta="File and comment" />
        </div>
      </div>

      {members.isLoading ? (
        <LoadingState />
      ) : members.isError ? (
        <ErrorState error={members.error} onRetry={() => void members.refetch()} inline />
      ) : (members.data?.length ?? 0) === 0 ? (
        <EmptyState
          inline
          title="No members on this project"
          message="Add people from the project's Members tab."
          action={
            <Link to={`/projects/${effectiveProjectId}?tab=members`} className="btn btn--primary btn--sm">
              Add members
            </Link>
          }
        />
      ) : (
        <Table columns={columns} rows={members.data ?? []} rowKey={(member) => member.id} caption="Project members" />
      )}

      {admin ? (
        <div className="card__footer">
          <span className="field__hint">
            As an administrator you bypass membership. Project roles are changed on the project's
            Members tab; system roles are changed below.
          </span>
        </div>
      ) : null}
    </>
  );
}

/* ==========================================================================
   System users (admin)
   ========================================================================== */

function SystemUsersTab() {
  const { user } = useAuthContext();
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [page, setPage] = useState(1);
  const [accountToToggle, setAccountToToggle] = useState<AdminUser | null>(null);

  const params = useMemo(
    () => ({
      search: search.trim() || undefined,
      system_role: roleFilter || undefined,
      page,
      page_size: 25,
      ordering: 'full_name',
    }),
    [search, roleFilter, page],
  );

  const users = useAdminUsers(params);
  const changeRole = useChangeUserRole();
  const setActive = useSetUserActive();

  const rows = users.data?.results ?? [];

  const columns: Array<Column<AdminUser>> = [
    {
      key: 'person',
      header: 'Person',
      render: (account) => (
        <span className="row row--nowrap">
          <Avatar name={account.full_name} size="sm" />
          <CellStack
            primary={
              account.id === user?.id ? (
                <span>
                  {account.full_name} <Badge tone="accent">you</Badge>
                </span>
              ) : (
                account.full_name
              )
            }
            secondary={account.email}
          />
        </span>
      ),
    },
    {
      key: 'role',
      header: 'System role',
      tight: true,
      render: (account) => (
        <Select
          label=""
          options={SYSTEM_ROLES.map((role) => ({ value: role, label: roleLabel(role) }))}
          value={account.system_role}
          disabled={changeRole.isPending || account.id === user?.id}
          title={account.id === user?.id ? 'You cannot change your own system role.' : undefined}
          onChange={(event) =>
            changeRole.mutate({ id: account.id, systemRole: event.target.value as SystemRole })
          }
        />
      ),
    },
    {
      key: 'status',
      header: 'Status',
      tight: true,
      render: (account) =>
        account.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="outline">Inactive</Badge>,
    },
    {
      key: 'joined',
      header: 'Joined',
      tight: true,
      render: (account) => (
        <span className="cell-stack__secondary" title={formatDate(account.date_joined)}>
          {formatRelative(account.date_joined)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      tight: true,
      render: (account) =>
        account.id === user?.id ? (
          <span className="field__hint">current session</span>
        ) : (
          <Button
            size="sm"
            variant={account.is_active ? 'danger-ghost' : 'secondary'}
            onClick={() => setAccountToToggle(account)}
          >
            {account.is_active ? 'Deactivate' : 'Activate'}
          </Button>
        ),
    },
  ];

  return (
    <>
      <div className="toolbar">
        <div className="toolbar__field toolbar__search">
          <Input
            label="Search"
            type="search"
            placeholder="Name or email…"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="toolbar__field">
          <label className="field__label" htmlFor="system-role-filter">
            System role
          </label>
          <select
            id="system-role-filter"
            className="select"
            value={roleFilter}
            onChange={(event) => {
              setRoleFilter(event.target.value);
              setPage(1);
            }}
          >
            <option value="">All roles</option>
            {SYSTEM_ROLES.map((role) => (
              <option key={role} value={role}>
                {roleLabel(role)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="card__body">
        <p className="field__hint">
          Deactivating an account keeps its tickets, comments and audit history attributable — accounts
          are never deleted. The last administrator cannot be demoted or deactivated; the API enforces
          that rule.
        </p>
      </div>

      {users.isLoading ? (
        <LoadingState />
      ) : users.isError ? (
        <ErrorState error={users.error} onRetry={() => void users.refetch()} inline />
      ) : rows.length === 0 ? (
        <EmptyState inline title="No accounts match" message="Try a different search term or role." />
      ) : (
        <>
          <Table
            columns={columns}
            rows={rows}
            rowKey={(account) => account.id}
            refreshing={users.isFetching}
            caption="System accounts"
          />
          <Pagination
            page={users.data?.page ?? 1}
            totalPages={users.data?.total_pages ?? 1}
            count={users.data?.count ?? 0}
            pageSize={users.data?.page_size ?? 25}
            onPageChange={setPage}
          />
        </>
      )}

      <ConfirmDialog
        open={accountToToggle !== null}
        title={accountToToggle?.is_active ? 'Deactivate this account?' : 'Activate this account?'}
        message={
          accountToToggle?.is_active
            ? `${accountToToggle.full_name} will no longer be able to sign in. Their history is kept.`
            : `${accountToToggle?.full_name ?? ''} will be able to sign in again.`
        }
        confirmLabel={accountToToggle?.is_active ? 'Deactivate' : 'Activate'}
        destructive={Boolean(accountToToggle?.is_active)}
        loading={setActive.isPending}
        onConfirm={() => {
          if (!accountToToggle) return;
          setActive.mutate(
            { id: accountToToggle.id, active: !accountToToggle.is_active },
            { onSuccess: () => setAccountToToggle(null) },
          );
        }}
        onCancel={() => setAccountToToggle(null)}
      />
    </>
  );
}
