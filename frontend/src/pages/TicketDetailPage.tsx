/**
 * Ticket detail — the screen the whole product centres on.
 *
 * Three things here are load-bearing and should not be "simplified":
 *
 * 1. **Transition buttons come from the API.** `GET /workflows/transitions/?ticket=<id>` returns the
 *    moves this caller may make *right now*, including the ones that are unavailable and why
 *    (`blocked_by`). The UI never hard-codes the state machine, so changing the lifecycle in the
 *    backend changes this screen without a frontend release.
 * 2. **Attachment download goes through `fetch`, not an `<a href>`.** The bytes live behind an
 *    authorising endpoint; a link click would be a plain navigation with no error reporting. See
 *    `handleDownload` — it fetches a blob with credentials and saves it via an object URL.
 * 3. **Status and assignee are not editable fields.** `PATCH` rejects both by design, so the edit
 *    form simply has no inputs for them and the dedicated controls are the only way to change them.
 */

import { useMemo, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, Avatar, MetaRow, PageHeader, Tabs } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Checkbox, Input, Select, Textarea, applyFieldErrors } from '../components/ui/Field';
import { ConfirmDialog, Modal } from '../components/ui/Modal';
import { EmptyState, ErrorState, FormAlert, LoadingState } from '../components/ui/States';
import { AssigneePicker } from '../components/ui/Pickers';
import { LabelBadge, PriorityBadge, SeverityBadge, StatusBadge, TypeBadge } from '../components/ui/Badge';
import { useProjectComponents, useProjectMembers } from '../features/projects/hooks';
import { useAuthContext } from '../features/auth/hooks/useAuthContext';
import {
  useAddComment,
  useAssignTicket,
  useAttachments,
  useComments,
  useDeleteAttachment,
  useDeleteComment,
  useTicket,
  useTicketChoices,
  useTicketHistory,
  useTicketTransitions,
  useTransitionTicket,
  useUpdateComment,
  useUpdateTicket,
  useUploadAttachment,
} from '../features/tickets/hooks';
import { apiDownload, saveBlob } from '../lib/http';
import {
  displayName,
  formatBytes,
  formatDate,
  formatDateTime,
  formatRelative,
  isCommentEditable,
  statusLabel,
  toDateInputValue,
} from '../lib/format';
import type { AllowedTransition, Attachment, Comment, Ticket } from '../types/api';

/** Reasons the backend reports in `blocked_by`, rendered as an explanation rather than a mystery. */
const BLOCKED_REASONS: Record<string, string> = {
  assignee_required: 'Assign the ticket first',
};

type TabId = 'discussion' | 'timeline' | 'attachments';

export function TicketDetailPage() {
  const { ticketId } = useParams<{ ticketId: string }>();
  const { user } = useAuthContext();
  const [tab, setTab] = useState<TabId>('discussion');

  const ticket = useTicket(ticketId);
  const transitions = useTicketTransitions(ticketId);
  const history = useTicketHistory(ticketId);
  const comments = useComments(ticketId);
  const attachments = useAttachments(ticketId);

  const members = useProjectMembers(ticket.data?.project.id);
  const components = useProjectComponents(ticket.data?.project.id);

  const transition = useTransitionTicket(ticketId ?? '');
  const assign = useAssignTicket(ticketId ?? '');
  const upload = useUploadAttachment(ticketId ?? '');
  const removeAttachment = useDeleteAttachment(ticketId ?? '');
  const addComment = useAddComment(ticketId ?? '');
  const updateComment = useUpdateComment(ticketId ?? '');
  const deleteComment = useDeleteComment(ticketId ?? '');

  const [pendingTransition, setPendingTransition] = useState<AllowedTransition | null>(null);
  const [transitionComment, setTransitionComment] = useState('');
  const [commentDraft, setCommentDraft] = useState('');
  const [editingComment, setEditingComment] = useState<Comment | null>(null);
  const [editingCommentBody, setEditingCommentBody] = useState('');
  const [commentToDelete, setCommentToDelete] = useState<Comment | null>(null);
  const [attachmentToDelete, setAttachmentToDelete] = useState<Attachment | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  /** Download failures cannot go through the mutation toast, so they get their own alert box. */
  const [downloadError, setDownloadError] = useState<string | null>(null);

  if (ticket.isLoading) return <LoadingState label="Loading ticket…" />;

  if (ticket.isError) {
    return (
      <Card>
        <ErrorState
          title="Could not load this ticket"
          error={ticket.error}
          onRetry={() => void ticket.refetch()}
        />
      </Card>
    );
  }

  if (!ticket.data) {
    return (
      <Card>
        <EmptyState title="Ticket not found" message="It may have been removed, or you may not have access to it." />
      </Card>
    );
  }

  const data = ticket.data;
  const allowed = transitions.data?.allowed ?? [];
  const isAssignee = Boolean(user && data.assignee && data.assignee.id === user.id);
  const isReporter = Boolean(user && data.reporter && data.reporter.id === user.id);

  /** Fetch the private file then save it — the session cookie travels with `fetch`, not with a link. */
  const handleDownload = async (attachment: Attachment) => {
    try {
      const blob = await apiDownload(attachment.download_url);
      saveBlob(blob, attachment.original_name);
    } catch (error) {
      // Surfaced through the same toast channel the mutations use.
      setDownloadError(error instanceof Error ? error.message : 'The file could not be downloaded.');
    }
  };

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Tickets', to: '/tickets' },
          { label: data.key },
        ]}
        title={data.title}
        subtitle={
          <span className="row">
            <Link to={`/projects/${data.project.id}`}>{data.project.name}</Link>
            <span className="breadcrumbs__sep">·</span>
            <span>reported {formatRelative(data.created_at)}</span>
          </span>
        }
        actions={
          <>
            <Button variant="secondary" onClick={() => void ticket.refetch()} loading={ticket.isFetching}>
              Refresh
            </Button>
            <Button variant="secondary" onClick={() => setEditOpen(true)}>
              Edit details
            </Button>
          </>
        }
      />

      <div className="grid grid--sidebar">
        <div className="stack">
          {/* ---- Header: key + badges + transitions ---------------------- */}
          <Card flush>
            <div className="ticket-header">
              <div className="row row--between">
                <span className="row">
                  <span className="badge badge--mono badge--outline">{data.key}</span>
                  <StatusBadge status={data.status} />
                  <PriorityBadge priority={data.priority} />
                  <SeverityBadge severity={data.severity} />
                  <TypeBadge type={data.type} />
                  {data.is_overdue ? <span className="badge badge--danger">Overdue</span> : null}
                </span>
                <span className="field__hint">Updated {formatRelative(data.updated_at)}</span>
              </div>

              <div>
                <p className="field__label">Move this ticket</p>
                {transitions.isLoading ? (
                  <LoadingState label="Checking available transitions…" />
                ) : transitions.isError ? (
                  <ErrorState
                    inline
                    title="Could not load transitions"
                    error={transitions.error}
                    onRetry={() => void transitions.refetch()}
                  />
                ) : allowed.length === 0 ? (
                  <p className="field__hint">
                    No status changes are available to you from{' '}
                    <strong>{statusLabel(data.status)}</strong>
                    {isAssignee || isReporter ? ' at the moment' : ' with your project role'}.
                  </p>
                ) : (
                  <div className="transition-bar" style={{ marginTop: 'var(--space-2)' }}>
                    {allowed.map((move) => (
                      <span className="transition-item" key={`${move.from_status}-${move.to_status}`}>
                        <Button
                          size="sm"
                          variant={move.to_status === 'BLOCKED' || move.to_status === 'REJECTED' ? 'danger-ghost' : 'secondary'}
                          disabled={!move.available}
                          title={
                            move.available
                              ? move.requires_comment
                                ? 'A comment is required for this transition.'
                                : undefined
                              : move.blocked_by.map((reason) => BLOCKED_REASONS[reason] ?? reason).join(', ')
                          }
                          onClick={() => {
                            setTransitionComment('');
                            setPendingTransition(move);
                          }}
                        >
                          {move.label}
                        </Button>
                        {!move.available ? (
                          <span className="transition-blocked">
                            {move.blocked_by.map((reason) => BLOCKED_REASONS[reason] ?? reason).join(', ')}
                          </span>
                        ) : move.requires_comment ? (
                          <span className="transition-blocked">comment required</span>
                        ) : null}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="card__body">
              <p className="description">{data.description}</p>
              {data.labels.length > 0 ? (
                <div className="chip-list" style={{ marginTop: 'var(--space-3)' }}>
                  {data.labels.map((label) => (
                    <LabelBadge key={label.id} name={label.name} color={label.color} />
                  ))}
                </div>
              ) : null}
            </div>
          </Card>

          {/* ---- Tabs: discussion / timeline / attachments --------------- */}
          <Card
            flush
            title={
              <Tabs
                tabs={[
                  { id: 'discussion', label: 'Discussion', count: comments.data?.length },
                  { id: 'timeline', label: 'Timeline', count: history.data?.length },
                  { id: 'attachments', label: 'Attachments', count: attachments.data?.length },
                ]}
                active={tab}
                onChange={(id) => setTab(id as TabId)}
              />
            }
          >
            {tab === 'discussion' ? (
              <>
                {comments.isLoading ? (
                  <LoadingState />
                ) : comments.isError ? (
                  <ErrorState error={comments.error} onRetry={() => void comments.refetch()} inline />
                ) : (comments.data?.length ?? 0) === 0 ? (
                  <EmptyState
                    inline
                    title="No comments yet"
                    message="Discussion is visible to everyone who can see this ticket."
                  />
                ) : (
                  <ul>
                    {comments.data?.map((comment) => (
                      <li className="comment" key={comment.id}>
                        <Avatar name={comment.author ? comment.author.full_name : null} />
                        <div className="comment__main">
                          <div className="comment__header">
                            <span className="comment__author">
                              {comment.author ? displayName(comment.author) : 'Deleted user'}
                            </span>
                            <span className="comment__time" title={formatDateTime(comment.created_at)}>
                              {formatRelative(comment.created_at)}
                            </span>
                            {comment.is_edited ? (
                              <span className="badge badge--outline">edited</span>
                            ) : null}
                          </div>

                          {editingComment?.id === comment.id ? (
                            <div className="stack stack--tight" style={{ marginTop: 'var(--space-2)' }}>
                              <Textarea
                                value={editingCommentBody}
                                onChange={(event) => setEditingCommentBody(event.target.value)}
                                rows={4}
                                aria-label="Edit comment"
                              />
                              <div className="row">
                                <Button
                                  size="sm"
                                  variant="primary"
                                  loading={updateComment.isPending}
                                  onClick={() =>
                                    updateComment.mutate(
                                      { commentId: comment.id, body: editingCommentBody },
                                      { onSuccess: () => setEditingComment(null) },
                                    )
                                  }
                                >
                                  Save
                                </Button>
                                <Button size="sm" variant="ghost" onClick={() => setEditingComment(null)}>
                                  Cancel
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <p className="comment__body">{comment.body}</p>
                          )}

                          <div className="comment__actions">
                            {/*
                              The edit control is offered only inside the window; the *authority* is
                              `apps.comments.services.update_comment`, which rejects a late edit with
                              `edit_window_closed`. `isCommentEditable` mirrors
                              COMMENT_EDIT_WINDOW_MINUTES for the affordance only.
                            */}
                            {isCommentEditable(comment, user?.id) ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                  setEditingComment(comment);
                                  setEditingCommentBody(comment.body);
                                }}
                              >
                                Edit
                              </Button>
                            ) : null}
                            {user && (comment.author?.id === user.id || user.system_role === 'ADMIN') ? (
                              <Button size="sm" variant="danger-ghost" onClick={() => setCommentToDelete(comment)}>
                                Delete
                              </Button>
                            ) : null}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}

                <form
                  className="composer"
                  onSubmit={(event: FormEvent) => {
                    event.preventDefault();
                    if (!commentDraft.trim()) return;
                    addComment.mutate(commentDraft.trim(), { onSuccess: () => setCommentDraft('') });
                  }}
                >
                  <Textarea
                    rows={3}
                    value={commentDraft}
                    onChange={(event) => setCommentDraft(event.target.value)}
                    placeholder="Add a comment…"
                    aria-label="New comment"
                  />
                  <div className="row row--between">
                    <span className="field__hint">Comments are visible to everyone on the project.</span>
                    <Button
                      type="submit"
                      variant="primary"
                      size="sm"
                      loading={addComment.isPending}
                      disabled={!commentDraft.trim()}
                    >
                      Comment
                    </Button>
                  </div>
                </form>
              </>
            ) : null}

            {tab === 'timeline' ? (
              history.isLoading ? (
                <LoadingState />
              ) : history.isError ? (
                <ErrorState error={history.error} onRetry={() => void history.refetch()} inline />
              ) : (history.data?.length ?? 0) === 0 ? (
                <EmptyState inline title="No status history" message="Status changes are recorded here." />
              ) : (
                <div className="card__body">
                  <ol className="timeline">
                    {history.data?.map((entry) => (
                      <li className="timeline__item" key={entry.id}>
                        <span className="timeline__dot" aria-hidden="true" />
                        <div className="timeline__header">
                          <span className="timeline__actor">{entry.changed_by_name}</span>
                          <span>
                            {entry.from_status ? (
                              <>
                                moved <StatusBadge status={entry.from_status} /> →
                              </>
                            ) : (
                              'created as'
                            )}{' '}
                            <StatusBadge status={entry.to_status} />
                          </span>
                          <span className="timeline__time" title={formatDateTime(entry.created_at)}>
                            {formatRelative(entry.created_at)}
                          </span>
                        </div>
                        {entry.comment ? <p className="timeline__comment">{entry.comment}</p> : null}
                      </li>
                    ))}
                  </ol>
                </div>
              )
            ) : null}

            {tab === 'attachments' ? (
              <>
                {attachments.isLoading ? (
                  <LoadingState />
                ) : attachments.isError ? (
                  <ErrorState error={attachments.error} onRetry={() => void attachments.refetch()} inline />
                ) : (attachments.data?.length ?? 0) === 0 ? (
                  <EmptyState
                    inline
                    title="No attachments"
                    message="Files are stored privately and streamed only to people who can see this ticket."
                  />
                ) : (
                  <ul className="attachment-list">
                    {attachments.data?.map((attachment) => (
                      <li className="attachment" key={attachment.id}>
                        <span className="attachment__icon" aria-hidden="true">
                          ⇩
                        </span>
                        <div className="attachment__main">
                          <p className="attachment__name" title={attachment.original_name}>
                            {attachment.original_name}
                          </p>
                          <p className="attachment__meta">
                            {formatBytes(attachment.size_bytes)} ·{' '}
                            {attachment.uploader ? displayName(attachment.uploader) : 'unknown'} ·{' '}
                            {formatRelative(attachment.created_at)}
                          </p>
                        </div>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void handleDownload(attachment)}
                        >
                          Download
                        </Button>
                        <Button
                          size="sm"
                          variant="danger-ghost"
                          onClick={() => setAttachmentToDelete(attachment)}
                        >
                          Delete
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}

                <div className="dropzone">
                  <label className="btn btn--secondary btn--sm" htmlFor="attachment-input">
                    Upload a file
                  </label>
                  <input
                    id="attachment-input"
                    type="file"
                    style={{ display: 'none' }}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) upload.mutate(file);
                      // Reset so choosing the same file twice still fires a change event.
                      event.target.value = '';
                    }}
                  />
                  {upload.isPending ? <span>Uploading…</span> : null}
                  <span>Extensions and size are validated by the server.</span>
                </div>
              </>
            ) : null}
          </Card>
        </div>

        {/* ---- Metadata + assignment ------------------------------------- */}
        <aside className="detail-aside detail-aside--sticky">
          <Card title="Details">
            <div className="meta-list">
              <MetaRow label="Reporter">
                <span className="row row--nowrap" style={{ justifyContent: 'flex-end' }}>
                  <Avatar name={data.reporter ? data.reporter.full_name : null} size="sm" />
                  {data.reporter ? displayName(data.reporter) : '—'}
                </span>
              </MetaRow>
              <MetaRow label="Assignee">
                {data.assignee ? (
                  <span className="row row--nowrap" style={{ justifyContent: 'flex-end' }}>
                    <Avatar name={data.assignee.full_name} size="sm" />
                    {displayName(data.assignee)}
                  </span>
                ) : (
                  'Unassigned'
                )}
              </MetaRow>
              <MetaRow label="Component">{data.component ? data.component.name : '—'}</MetaRow>
              <MetaRow label="Type">
                <TypeBadge type={data.type} />
              </MetaRow>
              <MetaRow label="Created">{formatDateTime(data.created_at)}</MetaRow>
              <MetaRow label="Updated">{formatDateTime(data.updated_at)}</MetaRow>
              <MetaRow label="Due">
                {data.due_date ? (
                  <span className={data.is_overdue ? 'badge badge--danger' : undefined}>
                    {formatDate(data.due_date)}
                  </span>
                ) : (
                  '—'
                )}
              </MetaRow>
              <MetaRow label="Resolved">{data.resolved_at ? formatDateTime(data.resolved_at) : '—'}</MetaRow>
              <MetaRow label="Closed">{data.closed_at ? formatDateTime(data.closed_at) : '—'}</MetaRow>
            </div>
          </Card>

          <Card title="Assignment" subtitle="Engineers and managers can be assigned work">
            {members.isLoading ? (
              <LoadingState />
            ) : members.isError ? (
              <ErrorState error={members.error} onRetry={() => void members.refetch()} inline />
            ) : (
              <div className="stack stack--tight">
                <AssigneePicker
                  members={members.data ?? []}
                  value={data.assignee?.id ?? ''}
                  currentUserId={user?.id}
                  loading={assign.isPending}
                  onChange={(userId) => assign.mutate(userId || null)}
                />
                <span className="field__hint">
                  {isAssignee
                    ? 'You own this ticket.'
                    : 'Changing the assignee uses the dedicated assignment endpoint.'}
                </span>
              </div>
            )}
          </Card>

          <Card title="Project">
            <div className="meta-list">
              <MetaRow label="Key">{data.project.key}</MetaRow>
              <MetaRow label="Name">
                <Link to={`/projects/${data.project.id}`}>{data.project.name}</Link>
              </MetaRow>
            </div>
            <Link
              to={`/tickets?project=${data.project.id}`}
              className="btn btn--ghost btn--sm btn--block"
              style={{ marginTop: 'var(--space-3)' }}
            >
              All tickets in this project
            </Link>
          </Card>
        </aside>
      </div>

      {/* ---- Transition dialog ------------------------------------------ */}
      <Modal
        open={pendingTransition !== null}
        onClose={() => setPendingTransition(null)}
        title={pendingTransition ? pendingTransition.label : 'Change status'}
        description={
          pendingTransition
            ? `${statusLabel(pendingTransition.from_status)} → ${statusLabel(pendingTransition.to_status)}`
            : undefined
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setPendingTransition(null)} disabled={transition.isPending}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={transition.isPending}
              disabled={Boolean(pendingTransition?.requires_comment) && transitionComment.trim() === ''}
              onClick={() => {
                if (!pendingTransition) return;
                transition.mutate(
                  { toStatus: pendingTransition.to_status, comment: transitionComment },
                  { onSuccess: () => setPendingTransition(null) },
                );
              }}
            >
              Apply
            </Button>
          </>
        }
      >
        <div className="stack">
          {pendingTransition && pendingTransition.blocked_by.length > 0 ? (
            <p className="form-alert" role="alert">
              {pendingTransition.blocked_by
                .map((reason) => BLOCKED_REASONS[reason] ?? reason.replace(/_/g, ' '))
                .join(', ')}
              . Close this dialog, then use the Assignment panel.
            </p>
          ) : null}
          {pendingTransition?.requires_comment ? (
            <Textarea
              label="Comment"
              required
              hint="This transition requires an explanation; it is recorded in the ticket's history."
              value={transitionComment}
              onChange={(event) => setTransitionComment(event.target.value)}
              rows={4}
            />
          ) : (
            <Textarea
              label="Comment (optional)"
              hint="Recorded in the ticket's history."
              value={transitionComment}
              onChange={(event) => setTransitionComment(event.target.value)}
              rows={3}
            />
          )}
          <FormAlert error={transition.isError ? transition.error : null} />
        </div>
      </Modal>

      {/* ---- Confirm dialogs -------------------------------------------- */}
      <ConfirmDialog
        open={commentToDelete !== null}
        title="Delete this comment?"
        message="The comment is soft-deleted: it disappears from the thread but stays in the audit trail."
        confirmLabel="Delete"
        destructive
        loading={deleteComment.isPending}
        onConfirm={() => {
          if (!commentToDelete) return;
          deleteComment.mutate(commentToDelete.id, { onSuccess: () => setCommentToDelete(null) });
        }}
        onCancel={() => setCommentToDelete(null)}
      />

      <ConfirmDialog
        open={attachmentToDelete !== null}
        title="Delete this attachment?"
        message={attachmentToDelete?.original_name}
        confirmLabel="Delete"
        destructive
        loading={removeAttachment.isPending}
        onConfirm={() => {
          if (!attachmentToDelete) return;
          removeAttachment.mutate(attachmentToDelete.id, { onSuccess: () => setAttachmentToDelete(null) });
        }}
        onCancel={() => setAttachmentToDelete(null)}
      />

      <EditTicketDialog
        open={editOpen}
        onClose={() => setEditOpen(false)}
        ticket={data}
        componentOptions={(components.data ?? [])
          .filter((component) => component.is_active || component.id === data.component?.id)
          .map((component) => ({ value: component.id, label: component.name }))}
      />

      {downloadError ? (
        <div className="toaster">
          <div className="toast toast--error" role="alert">
            <span aria-hidden="true">!</span>
            <div className="toast__main">
              <p className="toast__title">Download failed</p>
              <p className="toast__message">{downloadError}</p>
            </div>
            <Button variant="ghost" size="sm" iconOnly aria-label="Dismiss" onClick={() => setDownloadError(null)}>
              ✕
            </Button>
          </div>
        </div>
      ) : null}
    </>
  );
}

/**
 * The editable subset of a ticket.
 *
 * `status` and `assignee` are absent because `PATCH /tickets/<id>/` rejects them with
 * `use_transition_endpoint` / `use_assignment_endpoint`. Offering the inputs would mean offering a
 * request the backend is designed to refuse.
 */
const editSchema = z.object({
  title: z.string().trim().min(1, 'Give the ticket a title.').max(255, 'Use at most 255 characters.'),
  description: z.string().trim().min(1, 'Describe the problem or the work.'),
  type: z.string().min(1),
  priority: z.string().min(1),
  severity: z.string().min(1),
  component: z.string(),
  due_date: z.string(),
  keepLabels: z.boolean(),
});

type EditValues = z.infer<typeof editSchema>;

function EditTicketDialog({
  open,
  onClose,
  ticket,
  componentOptions,
}: {
  open: boolean;
  onClose: () => void;
  ticket: Ticket;
  componentOptions: Array<{ value: string; label: string }>;
}) {
  const choices = useTicketChoices();
  const update = useUpdateTicket(ticket.id);

  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    values: {
      title: ticket.title,
      description: ticket.description,
      type: ticket.type,
      priority: ticket.priority,
      severity: ticket.severity,
      component: ticket.component?.id ?? '',
      due_date: toDateInputValue(ticket.due_date),
      keepLabels: true,
    },
  });

  const onSubmit = handleSubmit((values) => {
    update.mutate(
      {
        title: values.title,
        description: values.description,
        type: values.type,
        priority: values.priority,
        severity: values.severity,
        component: values.component || null,
        due_date: values.due_date || null,
        // Labels are a list on the wire; the checkbox is the honest way to express "keep them",
        // since the form does not edit individual labels here.
        labels: values.keepLabels ? ticket.labels.map((label) => label.id) : [],
      },
      {
        onSuccess: () => {
          onClose();
          reset();
        },
        onError: (error) => applyFieldErrors(error, setError),
      },
    );
  });

  const pickerLabels = useMemo(() => ticket.labels, [ticket.labels]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="Edit ticket details"
      description="Status and assignee are changed with their own controls, not here."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={update.isPending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void onSubmit()} loading={update.isPending}>
            Save changes
          </Button>
        </>
      }
    >
      <form className="stack" onSubmit={(event) => { event.preventDefault(); void onSubmit(); }} noValidate>
        <FormAlert error={update.isError ? update.error : null} />

        <Input label="Title" required error={errors.title?.message} {...register('title')} />
        <Textarea label="Description" required rows={6} error={errors.description?.message} {...register('description')} />

        <div className="form-grid form-grid--2">
          <Select
            label="Type"
            options={(choices.data?.types ?? []).map((choice) => ({ value: choice.value, label: choice.label }))}
            error={errors.type?.message}
            {...register('type')}
          />
          <Select
            label="Priority"
            options={(choices.data?.priorities ?? []).map((choice) => ({ value: choice.value, label: choice.label }))}
            error={errors.priority?.message}
            {...register('priority')}
          />
          <Select
            label="Severity"
            options={(choices.data?.severities ?? []).map((choice) => ({ value: choice.value, label: choice.label }))}
            error={errors.severity?.message}
            {...register('severity')}
          />
          <Input label="Due date" type="date" error={errors.due_date?.message} {...register('due_date')} />
          <Select
            label="Component"
            options={[{ value: '', label: 'No component' }, ...componentOptions]}
            error={errors.component?.message}
            {...register('component')}
          />
        </div>

        {pickerLabels.length > 0 ? (
          <div className="field">
            <span className="field__label">Labels</span>
            <div className="chip-list">
              {pickerLabels.map((label) => (
                <LabelBadge key={label.id} name={label.name} color={label.color} />
              ))}
            </div>
            <Checkbox label="Keep these labels" {...register('keepLabels')} />
          </div>
        ) : null}
      </form>
    </Modal>
  );
}
