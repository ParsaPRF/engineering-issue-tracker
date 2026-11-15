/**
 * Ticket creation.
 *
 * Validation is split between the two parties that legitimately own different parts of it:
 *
 * * **zod** covers what the browser can know immediately — non-empty title, a project must be
 *   chosen, a description that is more than whitespace.
 * * **the API** covers everything else. `applyFieldErrors` copies the response's `fields` map onto
 *   the matching inputs, so a server rule (title too long, component not in the project) lands under
 *   the right field rather than only in a toast.
 *
 * `status` is deliberately absent: a new ticket always starts at `NEW`, and the serializer does not
 * accept the field. It appears in the UI only as a read-only note, so nobody hunts for the control.
 */

import { useEffect, useMemo } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, PageHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Select, Textarea, applyFieldErrors } from '../components/ui/Field';
import { FormAlert, LoadingState } from '../components/ui/States';
import { useProjectComponents, useProjectMembers, useProjects } from '../features/projects/hooks';
import { useCreateTicket, useTicketChoices } from '../features/tickets/hooks';
import { statusLabel } from '../lib/format';

const ticketSchema = z.object({
  project: z.string().min(1, 'Choose a project.'),
  title: z.string().trim().min(1, 'Give the ticket a title.').max(255, 'Use at most 255 characters.'),
  description: z.string().trim().min(1, 'Describe the problem or the work.'),
  type: z.string().min(1, 'Choose a type.'),
  priority: z.string().min(1, 'Choose a priority.'),
  severity: z.string().min(1, 'Choose a severity.'),
  component: z.string(),
  assignee: z.string(),
  due_date: z.string(),
});

type TicketFormValues = z.infer<typeof ticketSchema>;

export function TicketCreatePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialProject = searchParams.get('project') ?? '';

  const projects = useProjects({ status: 'ACTIVE', page_size: 100 });
  const choices = useTicketChoices();
  const create = useCreateTicket();

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    setError,
    formState: { errors },
  } = useForm<TicketFormValues>({
    resolver: zodResolver(ticketSchema),
    defaultValues: {
      project: initialProject,
      title: '',
      description: '',
      type: 'BUG',
      priority: 'MEDIUM',
      severity: 'MAJOR',
      component: '',
      assignee: '',
      due_date: '',
    },
  });

  const selectedProject = watch('project');

  // Component and assignee options depend on the chosen project — the API validates both against it,
  // so offering another project's members would be offering a 400.
  const members = useProjectMembers(selectedProject || undefined);
  const components = useProjectComponents(selectedProject || undefined);

  // A project change invalidates both dependent selections.
  useEffect(() => {
    setValue('component', '');
    setValue('assignee', '');
  }, [selectedProject, setValue]);

  useEffect(() => {
    if (create.isError) applyFieldErrors(create.error, setError);
  }, [create.isError, create.error, setError]);

  useEffect(() => {
    if (create.isSuccess) {
      // Land on the created ticket: the user's next action is almost always to read or triage it.
      navigate(`/tickets/${create.data.id}`, { replace: true });
    }
  }, [create.isSuccess, create.data, navigate]);

  const projectOptions = useMemo(
    () =>
      (projects.data?.results ?? []).map((project) => ({
        value: project.id,
        label: `${project.key} — ${project.name}`,
      })),
    [projects.data],
  );

  const componentOptions = useMemo(
    () => [
      { value: '', label: 'No component' },
      ...(components.data ?? [])
        .filter((component) => component.is_active)
        .map((component) => ({ value: component.id, label: component.name })),
    ],
    [components.data],
  );

  const assigneeOptions = useMemo(
    () => [
      { value: '', label: 'Unassigned' },
      ...(members.data ?? [])
        .filter((member) => member.is_active && (member.role === 'ENGINEER' || member.role === 'MANAGER'))
        .map((member) => ({ value: member.user.id, label: member.user_name })),
    ],
    [members.data],
  );

  const activeProjects = projects.data?.results ?? [];

  return (
    <>
      <PageHeader
        title="New ticket"
        subtitle="New tickets start in the New state; move them on with the transition buttons."
        breadcrumbs={[{ label: 'Tickets', to: '/tickets' }, { label: 'New' }]}
      />

      <div className="grid grid--sidebar">
        <Card>
          {projects.isLoading || choices.isLoading ? (
            <LoadingState label="Loading form options…" />
          ) : activeProjects.length === 0 ? (
            <div className="stack">
              <p className="description">
                You are not an active member of any non-archived project, so there is nowhere to file a
                ticket yet.
              </p>
              <Link to="/projects" className="btn btn--secondary" style={{ alignSelf: 'flex-start' }}>
                Browse projects
              </Link>
            </div>
          ) : (
            <form
              className="stack"
              onSubmit={handleSubmit((values) =>
                create.mutate({
                  project: values.project,
                  title: values.title,
                  description: values.description,
                  type: values.type,
                  priority: values.priority,
                  severity: values.severity,
                  component: values.component || null,
                  assignee: values.assignee || null,
                  due_date: values.due_date || null,
                }),
              )}
              noValidate
            >
              <FormAlert error={create.isError ? create.error : null} />

              <Select
                label="Project"
                required
                placeholder="Choose a project"
                options={projectOptions}
                error={errors.project?.message}
                {...register('project')}
              />

              <Input
                label="Title"
                required
                placeholder="A short summary of the problem"
                error={errors.title?.message}
                {...register('title')}
              />

              <Textarea
                label="Description"
                required
                rows={8}
                placeholder="What happened, what you expected, and any steps to reproduce."
                error={errors.description?.message}
                {...register('description')}
              />

              <div className="form-grid form-grid--2">
                <Select
                  label="Type"
                  required
                  options={(choices.data?.types ?? []).map((choice) => ({
                    value: choice.value,
                    label: choice.label,
                  }))}
                  error={errors.type?.message}
                  {...register('type')}
                />
                <Select
                  label="Priority"
                  required
                  options={(choices.data?.priorities ?? []).map((choice) => ({
                    value: choice.value,
                    label: choice.label,
                  }))}
                  error={errors.priority?.message}
                  {...register('priority')}
                />
                <Select
                  label="Severity"
                  required
                  options={(choices.data?.severities ?? []).map((choice) => ({
                    value: choice.value,
                    label: choice.label,
                  }))}
                  error={errors.severity?.message}
                  {...register('severity')}
                />
                <Input
                  label="Due date"
                  type="date"
                  hint="Optional. The ticket shows as overdue once this date passes."
                  error={errors.due_date?.message}
                  {...register('due_date')}
                />
                <Select
                  label="Component"
                  options={componentOptions}
                  disabled={!selectedProject || components.isLoading}
                  hint={!selectedProject ? 'Choose a project first.' : undefined}
                  error={errors.component?.message}
                  {...register('component')}
                />
                <Select
                  label="Assignee"
                  options={assigneeOptions}
                  disabled={!selectedProject || members.isLoading}
                  hint={
                    !selectedProject
                      ? 'Choose a project first.'
                      : 'Only engineers and managers can be assigned work.'
                  }
                  error={errors.assignee?.message}
                  {...register('assignee')}
                />
              </div>

              <div className="form-actions">
                <Button variant="secondary" onClick={() => navigate(-1)} disabled={create.isPending}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" loading={create.isPending}>
                  Create ticket
                </Button>
              </div>
            </form>
          )}
        </Card>

        <aside className="detail-aside">
          <Card title="How triage works here">
            <ul className="stack stack--tight">
              <li className="field__hint">
                <strong>Priority</strong> is how soon the work should be addressed (Lowest → Critical).
              </li>
              <li className="field__hint">
                <strong>Severity</strong> is how serious the technical impact is (Trivial → Blocker).
                They are independent axes.
              </li>
              <li className="field__hint">
                A new ticket starts as <strong>{statusLabel('NEW')}</strong>. Status changes go through
                the workflow's transition buttons, which the backend computes for your role.
              </li>
              <li className="field__hint">
                Reporters can file and comment; assignment is limited to engineers and managers.
              </li>
            </ul>
          </Card>
        </aside>
      </div>
    </>
  );
}
