/**
 * Ticket API calls.
 *
 * Two contract details that shape this module:
 *
 * * **`PATCH /tickets/<id>/` refuses `status` and `assignee`.** Sending either is an error by
 *   design (`use_transition_endpoint` / `use_assignment_endpoint`), which is why `TicketUpdatePayload`
 *   simply has no such fields and the two dedicated endpoints are separate functions. A type that
 *   allowed them would let a screen send a request the backend is built to reject.
 * * **Transitions are read before they are written.** `transitions` fetches what the caller may do
 *   next, including why a move is currently blocked; the UI renders buttons from that response and
 *   never from a hard-coded state machine.
 */

import { apiDelete, apiGet, apiPatch, apiPost, apiUpload, type Paginated } from '../../lib/http'
import type {
  AllowedTransition,
  Attachment,
  Comment,
  Component,
  Label,
  ProjectMembership,
  Ticket,
  TicketChoices,
  TicketHistoryEntry,
  TicketListItem,
  TicketTransitions,
  WorkflowCatalogue,
} from '../../types/api'
import type { QueryValue } from '../../lib/http'

/**
 * Params for the ticket list.
 *
 * Extends an index signature so the object can be used directly as a query key (`ListParams`) — the
 * key is derived from the params, so an extra key is part of the cached result's identity.
 */
export interface TicketListParams extends Record<string, QueryValue> {
  project?: string
  status?: string[]
  type?: string[]
  priority?: string[]
  severity?: string[]
  assignee?: string
  reporter?: string
  component?: string
  label?: string
  unassigned?: boolean
  overdue?: boolean
  open_only?: boolean
  due_before?: string
  due_after?: string
  search?: string
  ordering?: string
  page?: number
  page_size?: number
}

export interface TicketCreatePayload {
  project: string
  title: string
  description: string
  type: string
  priority: string
  severity: string
  component?: string | null
  assignee?: string | null
  due_date?: string | null
  labels?: string[]
}

/** Only the fields the API accepts on PATCH. `status` and `assignee` are absent on purpose. */
export interface TicketUpdatePayload {
  title?: string
  description?: string
  type?: string
  priority?: string
  severity?: string
  component?: string | null
  due_date?: string | null
  labels?: string[]
}

/** `GET /workflows/transitions/?ticket=<id>` payload, minus the wrapping type name. */
export interface TransitionsResponse extends TicketTransitions {
  allowed: AllowedTransition[]
}

export const ticketsApi = {
  list: (params: TicketListParams) =>
    apiGet<Paginated<TicketListItem>>('/tickets/', params as Record<string, QueryValue>),

  detail: (id: string) => apiGet<Ticket>(`/tickets/${id}/`),

  create: (payload: TicketCreatePayload) => apiPost<Ticket>('/tickets/', payload),

  /** PATCH accepts a partial payload; `status`/`assignee` must go through their own endpoints. */
  update: (id: string, payload: TicketUpdatePayload) =>
    apiPatch<Ticket>(`/tickets/${id}/`, payload),

  /** `assignee: null` unassigns. Not a PATCH — the API rejects `assignee` there. */
  assign: (id: string, assignee: string | null) =>
    apiPost<Ticket>(`/tickets/${id}/assign/`, { assignee }),

  /** The status change. `comment` is required by the backend for some target statuses. */
  transition: (id: string, to_status: string, comment?: string) =>
    apiPost<Ticket>(`/tickets/${id}/transitions/`, { to_status, comment: comment ?? '' }),

  /** What the caller may do next, from the state machine the backend owns. */
  transitions: (id: string) =>
    apiGet<TransitionsResponse>('/workflows/transitions/', { ticket: id }),

  history: (id: string) => apiGet<TicketHistoryEntry[]>(`/tickets/${id}/history/`),

  choices: () => apiGet<TicketChoices>('/tickets/choices/'),

  myAssignments: (includeDone: boolean, page?: number) =>
    apiGet<Paginated<TicketListItem>>('/tickets/my-assignments/', {
      include_done: includeDone ? 'true' : undefined,
      page,
    }),

  /** The full lifecycle definition, used by the Reports screen's workflow panel. */
  workflowCatalogue: () => apiGet<WorkflowCatalogue>('/workflows/'),

  // -- Collaboration --------------------------------------------------------

  comments: (ticketId: string) => apiGet<Comment[]>(`/tickets/${ticketId}/comments/`),

  addComment: (ticketId: string, body: string) =>
    apiPost<Comment>(`/tickets/${ticketId}/comments/`, { body }),

  updateComment: (commentId: string, body: string) =>
    apiPatch<Comment>(`/comments/${commentId}/`, { body }),

  deleteComment: (commentId: string) => apiDelete(`/comments/${commentId}/`),

  attachments: (ticketId: string) => apiGet<Attachment[]>(`/tickets/${ticketId}/attachments/`),

  /** Multipart upload; the backend's file field is named `file` (see `apiUpload`). */
  uploadAttachment: (ticketId: string, file: File) =>
    apiUpload<Attachment>(`/tickets/${ticketId}/attachments/`, file),

  deleteAttachment: (attachmentId: string) => apiDelete(`/attachments/${attachmentId}/`),

  // -- Labels ---------------------------------------------------------------

  /**
   * A project's labels, used to build the label filter.
   *
   * Paginated by the backend, so the caller asks for a page size large enough to cover a project's
   * taxonomy (labels are curated, not user-generated in bulk).
   */
  labels: (projectId: string) => apiGet<Paginated<Label>>('/labels/', { project: projectId, page_size: 100 }),

  // -- Unpaginated helpers --------------------------------------------------

  /**
   * Project members, used to populate the assignee picker.
   *
   * Declared here (rather than imported from the projects feature) to keep both feature modules
   * independently loadable; it is the same endpoint the project detail screen uses.
   */
  members: (projectId: string) => apiGet<ProjectMembership[]>(`/projects/${projectId}/members/`),

  /** Project components, for the ticket's component selector. */
  components: (projectId: string) => apiGet<Component[]>(`/projects/${projectId}/components/`),
}
