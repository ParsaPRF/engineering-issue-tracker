/**
 * Project detail.
 *
 * Three tabs, each with its own query and its own loading/empty/error state:
 *
 * * **Members** — managed through the directory search, which only admins and project managers may
 *   call; a non-manager sees a plain read-only list rather than a search box that would 403.
 * * **Components** — created, edited and retired (never deleted).
 * * **Tickets** — the shared `TicketFilterBar` with the project locked, so this tab and the global
 *   ticket list cannot drift apart.
 */

import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, CellStack, PageHeader, StatCard, Tabs } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge, PriorityBadge, SeverityBadge, StatusBadge } from '../components/ui/Badge';
import { Checkbox, Input, Select, Textarea, applyFieldErrors } from '../components/ui/Field';
import { ConfirmDialog, Modal } from '../components/ui/Modal';
import { EmptyState, ErrorState, FormAlert, LoadingState } from '../components/ui/States';
import { Pagination, Table, type Column } from '../components/ui/Table';
import { UserDirectoryPicker } from '../components/ui/Pickers';
import { TicketFilterBar } from '../components/TicketFilterBar';
import { TicketLinkCell } from '../components/DomainBits';
import { useAuthContext, canManageProject, useProjectRole } from '../features/auth/hooks/useAuthContext';
import {
  useAddMember,
  useArchiveProject,
  useCreateComponent,
  useDeactivateComponent,
  useProject,
  useProjectComponents,
  useProjectMembers,
  useProjectStats,
  useRemoveMember,
  useUpdateProject,
  useUpdateMemberRole,
  useUpdateComponent,
} from '../features/projects/hooks';
import { useTickets, useProjectLabels } from '../features/tickets/hooks';
import { useTicketFilters } from '../hooks/useTicketFilters';
import { BreakdownBars, PRIORITY_BAR_TONES, STATUS_BAR_TONES } from '../components/DomainBits';
import { PRIORITY_ORDER, STATUS_BAR_ORDER, formatDate, formatRelative, roleLabel } from '../lib/format';
import type { Component, ProjectMembership, ProjectRole, TicketListItem } from '../types/api';

type TabId = 'tickets' | 'members' | 'components';

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuthContext();
  const projectRole = useProjectRole(projectId);

  const tab = (searchParams.get('tab') as TabId | null) ?? 'tickets';
  const project = useProject(projectId);
  const stats = useProjectStats(projectId);
  // The component count is not part of the stats payload, so it comes from the project's own list.
  const components = useProjectComponents(projectId);
  const componentCount = components.data ? components.data.filter((component) => component.is_active).length : '—';

  const manage = canManageProject(user, projectRole) || project.data?.owner?.id === user?.id;

  if (project.isLoading) return <LoadingState label="Loading project…" />;

  if (project.isError) {
    return (
      <Card>
        <ErrorState title="Could not load this project" error={project.error} onRetry={() => void project.refetch()} />
      </Card>
    );
  }

  if (!project.data) {
    return (
      <Card>
        <EmptyState
          title="Project not found"
          message="It may not exist, or you may not be a member of it."
          action={
            <Link to="/projects" className="btn btn--secondary">
              Back to projects
            </Link>
          }
        />
      </Card>
    );
  }

  const data = project.data;

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: 'Projects', to: '/projects' }, { label: data.key }]}
        title={data.name}
        subtitle={
          <span className="row">
            <span className="badge badge--mono badge--outline">{data.key}</span>
            {data.status === 'ARCHIVED' ? (
              <Badge tone="outline">Archived</Badge>
            ) : (
              <Badge tone="success">Active</Badge>
            )}
            <span>
              Owner: {data.owner?.full_name ?? '—'}
              {projectRole ? ` · you are ${roleLabel(projectRole)}` : ''}
            </span>
          </span>
        }
        actions={
          <>
            <Button variant="secondary" onClick={() => void project.refetch()} loading={project.isFetching}>
              Refresh
            </Button>
            {manage ? <EditProjectButton name={data.name} description={data.description} projectId={data.id} /> : null}
            {manage ? (
              <ArchiveProjectButton projectId={data.id} archived={data.status === 'ARCHIVED'} />
            ) : null}
            <Link to={`/tickets/new?project=${data.id}`} className="btn btn--primary">
              New ticket
            </Link>
          </>
        }
      />

      <div className="stack">
        {data.description ? <p className="description">{data.description}</p> : null}

        <div className="stat-grid">
          <StatCard
            label="Total tickets"
            value={stats.data?.total_tickets ?? '—'}
            meta="All statuses"
            accent="accent"
          />
          <StatCard label="Open" value={stats.data?.open_tickets ?? '—'} meta="Work in flight" accent="warning" />
          <StatCard
            label="Resolved"
            value={stats.data?.resolved_tickets ?? '—'}
            meta={`${stats.data?.closed_tickets ?? '—'} closed`}
            accent="success"
          />
          <StatCard
            label="Blocked"
            value={stats.data?.blocked_tickets ?? '—'}
            meta={`${stats.data?.unassigned_tickets ?? '—'} unassigned open`}
            accent="danger"
          />
          <StatCard label="Members" value={data.member_count ?? '—'} meta="Active memberships" />
          <StatCard label="Components" value={componentCount} meta="Structure of the project" />
        </div>

        <div className="grid grid--2">
          <Card title="By priority">
            {stats.isLoading ? (
              <LoadingState />
            ) : stats.data ? (
              <BreakdownBars
                title="Tickets by priority"
                data={stats.data.by_priority}
                order={[...PRIORITY_ORDER]}
                toneByValue={PRIORITY_BAR_TONES}
              />
            ) : (
              <ErrorState inline error={stats.error} onRetry={() => void stats.refetch()} />
            )}
          </Card>
          <Card title="By status">
            {stats.isLoading ? (
              <LoadingState />
            ) : stats.data ? (
              <BreakdownBars
                title="Tickets by status"
                data={stats.data.by_status}
                order={STATUS_BAR_ORDER}
                toneByValue={STATUS_BAR_TONES}
              />
            ) : (
              <ErrorState inline error={stats.error} onRetry={() => void stats.refetch()} />
            )}
          </Card>
        </div>

        <Card
          flush
          title={
            <Tabs
              tabs={[
                { id: 'tickets', label: 'Tickets', count: stats.data?.total_tickets },
                { id: 'members', label: 'Members', count: data.member_count ?? undefined },
                { id: 'components', label: 'Components' },
              ]}
              active={tab}
              onChange={(id) => {
                const next = new URLSearchParams(searchParams);
                next.set('tab', id);
                setSearchParams(next, { replace: true });
              }}
            />
          }
        >
          {tab === 'tickets' ? <ProjectTicketsTab projectId={data.id} /> : null}
          {tab === 'members' ? (
            <MembersTab projectId={data.id} ownerId={data.owner?.id} canManage={manage} />
          ) : null}
          {tab === 'components' ? <ComponentsTab projectId={data.id} canManage={manage} /> : null}
        </Card>
      </div>
    </>
  );
}

/* ==========================================================================
   Tickets tab
   ========================================================================== */

function ProjectTicketsTab({ projectId }: { projectId: string }) {
  // The project is locked: this tab is scoped to it, and changing it here would be a navigation.
  const filters = useTicketFilters(projectId);
  const params = useMemo(
    () => ({
      project: projectId,
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
      page_size: 20,
    }),
    [filters, projectId],
  );

  const tickets = useTickets(params);
  const members = useProjectMembers(projectId);
  const components = useProjectComponents(projectId);
  const labels = useProjectLabels(projectId);

  const columns: Array<Column<TicketListItem>> = [
    { key: 'key', header: 'Key', render: (ticket) => <TicketLinkCell ticket={ticket} /> },
    {
      key: 'state',
      header: 'State',
      tight: true,
      render: (ticket) => (
        <span className="row" style={{ gap: 'var(--space-1)' }}>
          <StatusBadge status={ticket.status} />
          <PriorityBadge priority={ticket.priority} />
          <SeverityBadge severity={ticket.severity} />
        </span>
      ),
    },
    {
      key: 'assignee',
      header: 'Assignee',
      tight: true,
      render: (ticket) => ticket.assignee?.full_name ?? <span className="cell-stack__secondary">Unassigned</span>,
    },
    {
      key: 'updated_at',
      header: 'Updated',
      tight: true,
      render: (ticket) => <span className="cell-stack__secondary">{formatRelative(ticket.updated_at)}</span>,
    },
  ];

  return (
    <>
      <TicketFilterBar
        filters={filters}
        onChange={filters.setFilter}
        onReset={filters.reset}
        members={members.data ?? []}
        components={components.data ?? []}
        labels={labels.data?.results ?? []}
      />
      {tickets.isLoading ? (
        <LoadingState />
      ) : tickets.isError ? (
        <ErrorState error={tickets.error} onRetry={() => void tickets.refetch()} inline />
      ) : (tickets.data?.results.length ?? 0) === 0 ? (
        <EmptyState
          inline
          title="No tickets in this project"
          message="Adjust the filters above, or file the first ticket."
          action={
            <Link to={`/tickets/new?project=${projectId}`} className="btn btn--primary btn--sm">
              New ticket
            </Link>
          }
        />
      ) : (
        <>
          <Table
            columns={columns}
            rows={tickets.data?.results ?? []}
            rowKey={(ticket) => ticket.id}
            refreshing={tickets.isFetching}
            caption="Tickets in this project"
          />
          <Pagination
            page={tickets.data?.page ?? 1}
            totalPages={tickets.data?.total_pages ?? 1}
            count={tickets.data?.count ?? 0}
            pageSize={tickets.data?.page_size ?? 20}
            onPageChange={filters.setPage}
          />
        </>
      )}
    </>
  );
}

/* ==========================================================================
   Members tab
   ========================================================================== */

const PROJECT_ROLE_OPTIONS: Array<{ value: ProjectRole; label: string }> = [
  { value: 'REPORTER', label: 'Reporter' },
  { value: 'ENGINEER', label: 'Engineer' },
  { value: 'MANAGER', label: 'Project manager' },
];

function MembersTab({
  projectId,
  ownerId,
  canManage,
}: {
  projectId: string;
  ownerId: string | undefined;
  canManage: boolean;
}) {
  const [includeInactive, setIncludeInactive] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [memberToRemove, setMemberToRemove] = useState<ProjectMembership | null>(null);

  const members = useProjectMembers(projectId, includeInactive);
  const updateRole = useUpdateMemberRole(projectId);
  const removeMember = useRemoveMember(projectId);

  const columns: Array<Column<ProjectMembership>> = [
    {
      key: 'user',
      header: 'Person',
      render: (member) => (
        <CellStack primary={member.user_name} secondary={member.user_email} />
      ),
    },
    {
      key: 'role',
      header: 'Project role',
      tight: true,
      render: (member) =>
        canManage && member.is_active ? (
          <select
            className="select"
            style={{ width: 'auto', minWidth: 150 }}
            value={member.role}
            disabled={updateRole.isPending}
            aria-label={`Role for ${member.user_name}`}
            onChange={(event) =>
              updateRole.mutate({ membershipId: member.id, role: event.target.value as ProjectRole })
            }
          >
            {PROJECT_ROLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <Badge tone={member.role === 'MANAGER' ? 'accent' : 'neutral'}>{roleLabel(member.role)}</Badge>
        ),
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
    {
      key: 'actions',
      header: '',
      align: 'right',
      tight: true,
      render: (member) =>
        canManage && member.is_active ? (
          <div className="row" style={{ justifyContent: 'flex-end', gap: 'var(--space-1)' }}>
            {member.user.id === ownerId ? (
              <span className="field__hint" title="The project owner must keep the manager role.">
                owner
              </span>
            ) : null}
            <Button size="sm" variant="danger-ghost" onClick={() => setMemberToRemove(member)}>
              Remove
            </Button>
          </div>
        ) : null,
    },
  ];

  return (
    <>
      <div className="toolbar">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(event) => setIncludeInactive(event.target.checked)}
          />
          <span>Show inactive members</span>
        </label>
        <div className="toolbar__actions">
          {canManage ? (
            <Button variant="primary" size="sm" onClick={() => setAddOpen(true)}>
              Add member
            </Button>
          ) : (
            <span className="field__hint">Only project managers can change membership.</span>
          )}
        </div>
      </div>

      {members.isLoading ? (
        <LoadingState />
      ) : members.isError ? (
        <ErrorState error={members.error} onRetry={() => void members.refetch()} inline />
      ) : (members.data?.length ?? 0) === 0 ? (
        <EmptyState inline title="No members" message="Add the first person to this project." />
      ) : (
        <Table
          columns={columns}
          rows={members.data ?? []}
          rowKey={(member) => member.id}
          caption="Project members"
        />
      )}

      <AddMemberDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        projectId={projectId}
        existingIds={(members.data ?? []).map((member) => member.user.id)}
      />

      <ConfirmDialog
        open={memberToRemove !== null}
        title="Remove this member?"
        message={`${memberToRemove?.user_name ?? ''} loses access to this project. Their tickets and history are kept.`}
        confirmLabel="Remove"
        destructive
        loading={removeMember.isPending}
        onConfirm={() => {
          if (!memberToRemove) return;
          removeMember.mutate(memberToRemove.id, { onSuccess: () => setMemberToRemove(null) });
        }}
        onCancel={() => setMemberToRemove(null)}
      />
    </>
  );
}

function AddMemberDialog({
  open,
  onClose,
  projectId,
  existingIds,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  existingIds: string[];
}) {
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [role, setRole] = useState<ProjectRole>('ENGINEER');
  const addMember = useAddMember(projectId);

  // Reset the picker each time the dialog opens, so a previous selection cannot be re-submitted.
  useEffect(() => {
    if (open) {
      setSelectedUser(null);
      setRole('ENGINEER');
    }
  }, [open]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="Add a project member"
      description="Search the directory, then choose their role inside this project."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={addMember.isPending}>
            Close
          </Button>
          <Button
            variant="primary"
            loading={addMember.isPending}
            disabled={!selectedUser}
            onClick={() => {
              if (!selectedUser) return;
              addMember.mutate(
                { userId: selectedUser, role },
                { onSuccess: () => setSelectedUser(null) },
              );
            }}
          >
            Add member
          </Button>
        </>
      }
    >
      <div className="stack">
        <Select
          label="Project role"
          options={PROJECT_ROLE_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
          value={role}
          onChange={(event) => setRole(event.target.value as ProjectRole)}
          hint="Reporters can file and comment; engineers can be assigned work; managers administer the project."
        />

        <UserDirectoryPicker onSelect={setSelectedUser} excludeUserIds={existingIds} />

        {selectedUser ? (
          <p className="form-alert" role="status">
            Selected user {selectedUser}. Choosing a role and pressing “Add member” grants access.
          </p>
        ) : null}
      </div>
    </Modal>
  );
}

/* ==========================================================================
   Components tab
   ========================================================================== */

function ComponentsTab({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const [includeInactive, setIncludeInactive] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [componentToDeactivate, setComponentToDeactivate] = useState<Component | null>(null);
  const [componentToEdit, setComponentToEdit] = useState<Component | null>(null);

  const components = useProjectComponents(projectId, includeInactive);
  const deactivate = useDeactivateComponent(projectId);

  const columns: Array<Column<Component>> = [
    {
      key: 'name',
      header: 'Component',
      render: (component) => (
        <CellStack primary={component.name} secondary={component.description || undefined} />
      ),
    },
    {
      key: 'lead',
      header: 'Lead',
      tight: true,
      render: (component) => component.lead?.full_name ?? '—',
    },
    {
      key: 'status',
      header: 'Status',
      tight: true,
      render: (component) =>
        component.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="outline">Inactive</Badge>,
    },
    {
      key: 'created',
      header: 'Created',
      tight: true,
      render: (component) => <span className="cell-stack__secondary">{formatDate(component.created_at)}</span>,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      tight: true,
      render: (component) =>
        canManage ? (
          <div className="row" style={{ justifyContent: 'flex-end', gap: 'var(--space-1)' }}>
            <Button size="sm" variant="ghost" onClick={() => setComponentToEdit(component)}>
              Edit
            </Button>
            {component.is_active ? (
              <Button size="sm" variant="danger-ghost" onClick={() => setComponentToDeactivate(component)}>
                Deactivate
              </Button>
            ) : null}
          </div>
        ) : null,
    },
  ];

  return (
    <>
      <div className="toolbar">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(event) => setIncludeInactive(event.target.checked)}
          />
          <span>Show inactive components</span>
        </label>
        <div className="toolbar__actions">
          {canManage ? (
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              New component
            </Button>
          ) : (
            <span className="field__hint">Only project managers can manage components.</span>
          )}
        </div>
      </div>

      {components.isLoading ? (
        <LoadingState />
      ) : components.isError ? (
        <ErrorState error={components.error} onRetry={() => void components.refetch()} inline />
      ) : (components.data?.length ?? 0) === 0 ? (
        <EmptyState
          inline
          title="No components"
          message="Components group tickets by the part of the system they touch."
        />
      ) : (
        <Table
          columns={columns}
          rows={components.data ?? []}
          rowKey={(component) => component.id}
          caption="Project components"
        />
      )}

      <CreateComponentDialog open={createOpen} onClose={() => setCreateOpen(false)} projectId={projectId} />

      <EditComponentDialog
        key={componentToEdit?.id ?? 'no-component'}
        component={componentToEdit}
        onClose={() => setComponentToEdit(null)}
        projectId={projectId}
      />

      <ConfirmDialog
        open={componentToDeactivate !== null}
        title="Deactivate this component?"
        message={`${componentToDeactivate?.name ?? ''} stops being selectable on new tickets. Existing tickets keep it.`}
        confirmLabel="Deactivate"
        loading={deactivate.isPending}
        onConfirm={() => {
          if (!componentToDeactivate) return;
          deactivate.mutate(componentToDeactivate.id, { onSuccess: () => setComponentToDeactivate(null) });
        }}
        onCancel={() => setComponentToDeactivate(null)}
      />
    </>
  );
}

const componentSchema = z.object({
  name: z.string().trim().min(1, 'Give the component a name.').max(100, 'Use at most 100 characters.'),
  description: z.string().max(2000, 'Use at most 2000 characters.'),
});

type ComponentValues = z.infer<typeof componentSchema>;

function CreateComponentDialog({
  open,
  onClose,
  projectId,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
}) {
  const create = useCreateComponent(projectId);
  const members = useProjectMembers(projectId);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<ComponentValues>({
    resolver: zodResolver(componentSchema),
    defaultValues: { name: '', description: '' },
  });

  useEffect(() => {
    if (create.isError) applyFieldErrors(create.error, setError);
  }, [create.isError, create.error, setError]);

  const onSubmit = handleSubmit((values) => {
    create.mutate(
      { name: values.name, description: values.description },
      {
        onSuccess: () => {
          reset();
          onClose();
        },
      },
    );
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New component"
      description={`Components group tickets by area. Leading a component is optional (${members.data?.length ?? 0} member(s) available).`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void onSubmit()} loading={create.isPending}>
            Create component
          </Button>
        </>
      }
    >
      <form className="stack" onSubmit={(event) => { event.preventDefault(); void onSubmit(); }} noValidate>
        <FormAlert error={create.isError ? create.error : null} />
        <Input label="Name" required placeholder="Payments API" error={errors.name?.message} {...register('name')} />
        <Textarea label="Description" rows={3} error={errors.description?.message} {...register('description')} />
      </form>
    </Modal>
  );
}

/**
 * Edit a component's name, description, lead and active flag.
 *
 * Updates go through `/components/<id>/` rather than the project-nested path — a component lives in
 * exactly one project, so repeating the project in the URL adds nothing.
 */
function EditComponentDialog({
  component,
  onClose,
  projectId,
}: {
  component: Component | null;
  onClose: () => void;
  projectId: string;
}) {
  const update = useUpdateComponent(projectId);
  const members = useProjectMembers(projectId);

  const leadOptions = useMemo(
    () => [
      { value: '', label: 'No lead' },
      ...(members.data ?? [])
        .filter((member) => member.is_active && (member.role === 'ENGINEER' || member.role === 'MANAGER'))
        .map((member) => ({ value: member.user.id, label: member.user_name })),
    ],
    [members.data],
  );

  // The dialog is mounted with the component it edits, so `key` on the parent resets this form.
  const initialLead = component?.lead?.id ?? '';

  return (
    <Modal
      open={component !== null}
      onClose={onClose}
      title={component ? `Edit ${component.name}` : 'Edit component'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={update.isPending}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="edit-component-form"
            variant="primary"
            loading={update.isPending}
          >
            Save changes
          </Button>
        </>
      }
    >
      <form
        id="edit-component-form"
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          update.mutate(
            {
              componentId: component?.id ?? '',
              payload: {
                name: String(form.get('name') ?? ''),
                description: String(form.get('description') ?? ''),
                lead: String(form.get('lead') ?? '') || null,
                is_active: form.get('is_active') === 'on',
              },
            },
            { onSuccess: onClose },
          );
        }}
      >
        <Input
          label="Name"
          name="name"
          required
          defaultValue={component?.name ?? ''}
          maxLength={100}
        />
        <Textarea label="Description" name="description" rows={3} defaultValue={component?.description ?? ''} />
        <Select label="Lead" name="lead" options={leadOptions} defaultValue={initialLead} />
        <Checkbox
          label="Active (selectable on new tickets)"
          name="is_active"
          defaultChecked={component?.is_active ?? true}
        />
      </form>
    </Modal>
  );
}

/* ==========================================================================
   Header actions
   ========================================================================== */

const editSchema = z.object({
  name: z.string().trim().min(1, 'Give the project a name.').max(200, 'Use at most 200 characters.'),
  description: z.string().max(2000, 'Use at most 2000 characters.'),
});

function EditProjectButton({
  projectId,
  name,
  description,
}: {
  projectId: string;
  name: string;
  description: string;
}) {
  const [open, setOpen] = useState(false);
  const update = useUpdateProject(projectId);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.infer<typeof editSchema>>({
    resolver: zodResolver(editSchema),
    values: { name, description },
  });

  useEffect(() => {
    if (update.isError) applyFieldErrors(update.error, setError);
  }, [update.isError, update.error, setError]);

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Edit project
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Edit project"
        description="The key is immutable: it prefixes every ticket."
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)} disabled={update.isPending}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={update.isPending}
              onClick={() =>
                void handleSubmit((values) =>
                  update.mutate(values, { onSuccess: () => setOpen(false) }),
                )()
              }
            >
              Save
            </Button>
          </>
        }
      >
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSubmit((values) => update.mutate(values, { onSuccess: () => setOpen(false) }))();
          }}
          noValidate
        >
          <FormAlert error={update.isError ? update.error : null} />
          <Input label="Name" required error={errors.name?.message} {...register('name')} />
          <Textarea label="Description" rows={4} error={errors.description?.message} {...register('description')} />
        </form>
      </Modal>
    </>
  );
}

function ArchiveProjectButton({ projectId, archived }: { projectId: string; archived: boolean }) {
  const [open, setOpen] = useState(false);
  const archive = useArchiveProject(projectId);

  return (
    <>
      <Button variant={archived ? 'secondary' : 'danger-ghost'} onClick={() => setOpen(true)}>
        {archived ? 'Restore' : 'Archive'}
      </Button>
      <ConfirmDialog
        open={open}
        title={archived ? 'Restore this project?' : 'Archive this project?'}
        message={
          archived
            ? 'The project becomes active again and accepts new tickets.'
            : 'An archived project keeps all its history but stops accepting new tickets.'
        }
        confirmLabel={archived ? 'Restore' : 'Archive'}
        destructive={!archived}
        loading={archive.isPending}
        onConfirm={() => archive.mutate(archived, { onSuccess: () => setOpen(false) })}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}
