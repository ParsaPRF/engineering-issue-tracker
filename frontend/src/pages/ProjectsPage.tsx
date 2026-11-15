/**
 * Projects list.
 *
 * The "New project" action is behind `ManagerOnly` because the API refuses project creation from
 * anyone else (`can_create_project`) — showing the button to an engineer would only produce a 403
 * they cannot act on. That gate is presentation; the endpoint is the authority.
 */

import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, CellStack, PageHeader, StatCard } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Textarea, applyFieldErrors } from '../components/ui/Field';
import { Modal } from '../components/ui/Modal';
import { EmptyState, ErrorState, FormAlert, LoadingState } from '../components/ui/States';
import { Pagination, Table, type Column } from '../components/ui/Table';
import { Badge } from '../components/ui/Badge';
import { ManagerOnly } from '../features/auth/ProtectedRoute';
import { useCreateProject, useProjects } from '../features/projects/hooks';
import { formatDate } from '../lib/format';
import type { Project } from '../types/api';

/**
 * Project key rules, mirroring the backend's `project_key_validator`: 2–10 characters, uppercase
 * letters and digits, starting with a letter. The server upper-cases before validating, so the input
 * accepts lower case and normalises on submit — the same ordering the serializer documents.
 */
const createSchema = z.object({
  key: z
    .string()
    .trim()
    .min(2, 'Use at least 2 characters.')
    .max(10, 'Use at most 10 characters.')
    .regex(/^[A-Za-z][A-Za-z0-9]{1,9}$/, 'Start with a letter; use only letters and digits (e.g. ENG, PAY2).'),
  name: z.string().trim().min(1, 'Give the project a name.').max(200, 'Use at most 200 characters.'),
  description: z.string().max(2000, 'Use at most 2000 characters.'),
});

type CreateValues = z.infer<typeof createSchema>;

export function ProjectsPage() {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);

  const params = useMemo(
    () => ({
      search: search.trim() || undefined,
      status: status || undefined,
      page,
      page_size: 25,
      ordering: 'name',
    }),
    [search, status, page],
  );

  const projects = useProjects(params);
  const rows = projects.data?.results ?? [];

  const counts = useMemo(() => {
    const members = rows.reduce((sum, project) => sum + (project.member_count ?? 0), 0);
    const tickets = rows.reduce((sum, project) => sum + (project.ticket_count ?? 0), 0);
    const open = rows.reduce((sum, project) => sum + (project.open_ticket_count ?? 0), 0);
    return { members, tickets, open };
  }, [rows]);

  const columns: Array<Column<Project>> = [
    {
      key: 'project',
      header: 'Project',
      render: (project) => (
        <CellStack
          primary={<Link to={`/projects/${project.id}`}>{project.key}</Link>}
          secondary={
            <>
              {project.name}
              {project.description ? <span> · {trim(project.description, 90)}</span> : null}
            </>
          }
        />
      ),
    },
    {
      key: 'status',
      header: 'Status',
      tight: true,
      render: (project) =>
        project.status === 'ARCHIVED' ? (
          <Badge tone="outline">Archived</Badge>
        ) : (
          <Badge tone="success">Active</Badge>
        ),
    },
    {
      key: 'owner',
      header: 'Owner',
      render: (project) => project.owner?.full_name ?? '—',
    },
    {
      key: 'members',
      header: 'Members',
      align: 'right',
      tight: true,
      render: (project) => project.member_count ?? 0,
    },
    {
      key: 'tickets',
      header: 'Tickets',
      align: 'right',
      tight: true,
      render: (project) => (
        <CellStack primary={project.ticket_count ?? 0} secondary={`${project.open_ticket_count ?? 0} open`} />
      ),
    },
    {
      key: 'created',
      header: 'Created',
      tight: true,
      render: (project) => <span className="cell-stack__secondary">{formatDate(project.created_at)}</span>,
    },
  ];

  return (
    <>
      <PageHeader
        title="Projects"
        subtitle={
          projects.data
            ? `${projects.data.count} project(s) visible to you.`
            : 'Every project you are a member of, plus archived ones.'
        }
        actions={
          <>
            <Button variant="secondary" onClick={() => void projects.refetch()} loading={projects.isFetching}>
              Refresh
            </Button>
            <ManagerOnly>
              <Button variant="primary" onClick={() => setCreateOpen(true)}>
                New project
              </Button>
            </ManagerOnly>
          </>
        }
      />

      <div className="stack">
        <div className="stat-grid">
          <StatCard label="Projects on this page" value={rows.length} meta={`${projects.data?.count ?? 0} total`} accent="accent" />
          <StatCard label="Members" value={counts.members} meta="Across the projects shown" />
          <StatCard label="Open tickets" value={counts.open} meta="Currently in progress or waiting" accent="warning" />
          <StatCard label="Tickets" value={counts.tickets} meta="All statuses" accent="success" />
        </div>

        <Card flush>
          <form className="toolbar" onSubmit={(event) => event.preventDefault()}>
            <div className="toolbar__field toolbar__search">
              <Input
                label="Search"
                type="search"
                placeholder="Name, key or description…"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
              />
            </div>
            <div className="toolbar__field">
              <label className="field__label" htmlFor="project-status-filter">
                Status
              </label>
              <select
                id="project-status-filter"
                className="select"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setPage(1);
                }}
              >
                <option value="">All statuses</option>
                <option value="ACTIVE">Active</option>
                <option value="ARCHIVED">Archived</option>
              </select>
            </div>
          </form>

          {projects.isLoading ? (
            <LoadingState label="Loading projects…" />
          ) : projects.isError ? (
            <ErrorState
              title="Could not load projects"
              error={projects.error}
              onRetry={() => void projects.refetch()}
            />
          ) : rows.length === 0 ? (
            <EmptyState
              title={search || status ? 'No projects match these filters' : 'No projects yet'}
              message={
                search || status
                  ? 'Try a different search term or clear the status filter.'
                  : 'You are not a member of any project. A project manager or administrator can add you.'
              }
              action={
                search || status ? (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setSearch('');
                      setStatus('');
                      setPage(1);
                    }}
                  >
                    Clear filters
                  </Button>
                ) : (
                  <ManagerOnly>
                    <Button variant="primary" onClick={() => setCreateOpen(true)}>
                      New project
                    </Button>
                  </ManagerOnly>
                )
              }
            />
          ) : (
            <>
              <Table
                columns={columns}
                rows={rows}
                rowKey={(project) => project.id}
                refreshing={projects.isFetching}
                caption="Projects"
              />
              <Pagination
                page={projects.data?.page ?? 1}
                totalPages={projects.data?.total_pages ?? 1}
                count={projects.data?.count ?? 0}
                pageSize={projects.data?.page_size ?? 25}
                onPageChange={setPage}
              />
            </>
          )}
        </Card>
      </div>

      <CreateProjectDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  );
}

/** Shorten a long description for the table's secondary line. */
function trim(value: string, length: number): string {
  const single = value.replace(/\s+/g, ' ').trim();
  return single.length > length ? `${single.slice(0, length - 1)}…` : single;
}

function CreateProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateProject();
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { key: '', name: '', description: '' },
  });

  useEffect(() => {
    if (create.isError) applyFieldErrors(create.error, setError);
  }, [create.isError, create.error, setError]);

  const onSubmit = handleSubmit((values) => {
    create.mutate(
      {
        // The serializer upper-cases before validating, but sending it upper-case keeps the
        // response's key identical to what the user typed.
        key: values.key.trim().toUpperCase(),
        name: values.name,
        description: values.description,
      },
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
      title="New project"
      description="The key prefixes every ticket in this project (ENG → ENG-1042) and cannot change later."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void onSubmit()} loading={create.isPending}>
            Create project
          </Button>
        </>
      }
    >
      <form className="stack" onSubmit={(event) => { event.preventDefault(); void onSubmit(); }} noValidate>
        <FormAlert error={create.isError ? create.error : null} />
        <Input
          label="Key"
          required
          placeholder="ENG"
          maxLength={10}
          hint="2–10 letters or digits, starting with a letter."
          error={errors.key?.message}
          {...register('key')}
        />
        <Input label="Name" required placeholder="Engineering Platform" error={errors.name?.message} {...register('name')} />
        <Textarea
          label="Description"
          rows={4}
          placeholder="What this project covers."
          error={errors.description?.message}
          {...register('description')}
        />
      </form>
    </Modal>
  );
}
