/**
 * Ticket hooks.
 *
 * The invalidation strategy is intentionally blunt: after a mutation, invalidate the ticket's own
 * detail (or the whole ticket key space for a collection change) and be done. Optimistic updates
 * would save one fetch and cost a class of bugs where the UI shows a value the server never
 * accepted — a poor trade for a tracker, where being *right* about status matters more than being
 * instant.
 *
 * The one asymmetry: a transition invalidates the transitions query too, because the allowed moves
 * change with the status, and the buttons must be re-read from the backend rather than recomputed.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, ensureCsrfCookie } from '../../lib/http'
import { queryKeys } from '../../lib/queryClient'
import { useToast } from '../../components/toast/ToastProvider'
import { ticketsApi, type TicketListParams, type TicketUpdatePayload } from './api'
import type { Ticket } from '../../types/api'
import type { TicketCreatePayload } from './api'

/** Query parameters for the ticket list; arrays are joined into comma-separated values. */
export function useTickets(params: TicketListParams) {
  return useQuery({
    queryKey: queryKeys.tickets.list(params),
    queryFn: () => ticketsApi.list(params),
  })
}

export function useTicket(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.tickets.detail(id ?? ''),
    queryFn: () => ticketsApi.detail(id as string),
    enabled: Boolean(id),
  })
}

export function useTicketChoices() {
  return useQuery({
    queryKey: queryKeys.tickets.choices,
    queryFn: () => ticketsApi.choices(),
    // Enumerations change only when the backend is redeployed; a long stale time keeps the filter
    // bar from refetching on every screen mount.
    staleTime: 10 * 60_000,
  })
}

/**
 * The moves the caller may make next.
 *
 * Fetched per ticket and never cached across tickets. `available: false` entries are still returned
 * — they carry `blocked_by`, which the detail screen renders as the reason a button is greyed out.
 */
export function useTicketTransitions(ticketId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.tickets.transitions(ticketId ?? ''),
    queryFn: () => ticketsApi.transitions(ticketId as string),
    enabled: Boolean(ticketId),
    staleTime: 0,
  })
}

export function useTicketHistory(ticketId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.tickets.history(ticketId ?? ''),
    queryFn: () => ticketsApi.history(ticketId as string),
    enabled: Boolean(ticketId),
  })
}

export function useMyAssignments(includeDone: boolean, page: number) {
  return useQuery({
    queryKey: queryKeys.tickets.myAssignments(includeDone),
    queryFn: () => ticketsApi.myAssignments(includeDone, page),
  })
}

export function useWorkflowCatalogue() {
  return useQuery({
    queryKey: queryKeys.workflows.catalogue,
    queryFn: () => ticketsApi.workflowCatalogue(),
    staleTime: 10 * 60_000,
  })
}

/**
 * A project's labels, for the ticket list's label filter.
 *
 * Disabled without a project, because `/labels/` is scoped by project and an unscoped call would
 * return every label the caller can see across the whole installation.
 */
export function useProjectLabels(projectId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.labels.list(projectId ?? ''),
    queryFn: () => ticketsApi.labels(projectId as string),
    enabled: Boolean(projectId),
    staleTime: 5 * 60_000,
  })
}

/** Invalidate everything that shows a ticket's data in a list or on the dashboard. */
function invalidateTicketCollections(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.lists() })
  void queryClient.invalidateQueries({ queryKey: ['tickets', 'my-assignments'] })
  void queryClient.invalidateQueries({ queryKey: ['reports'] })
  void queryClient.invalidateQueries({ queryKey: ['projects'] })
}

export function useCreateTicket() {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (payload: TicketCreatePayload) => {
      await ensureCsrfCookie()
      return ticketsApi.create(payload)
    },
    onSuccess: (ticket) => {
      invalidateTicketCollections(queryClient)
      toast.success('Ticket created', `${ticket.key}: ${ticket.title}`)
    },
    // Field errors are applied to the form by the screen; the toast carries the summary.
    onError: (error) => toast.error('Could not create the ticket', detailOf(error)),
  })
}

export function useUpdateTicket(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (payload: TicketUpdatePayload) => {
      await ensureCsrfCookie()
      return ticketsApi.update(id, payload)
    },
    onSuccess: (ticket) => {
      queryClient.setQueryData<Ticket>(queryKeys.tickets.detail(id), ticket)
      invalidateTicketCollections(queryClient)
      toast.success('Ticket updated')
    },
    onError: (error) => toast.error('Could not update the ticket', detailOf(error)),
  })
}

export function useAssignTicket(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (assignee: string | null) => {
      await ensureCsrfCookie()
      return ticketsApi.assign(id, assignee)
    },
    onSuccess: (ticket) => {
      queryClient.setQueryData<Ticket>(queryKeys.tickets.detail(id), ticket)
      invalidateTicketCollections(queryClient)
      // Reassignment can unlock an assignee-required transition, so the move list is stale too.
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.transitions(id) })
      toast.success(ticket.assignee ? `Assigned to ${ticket.assignee.full_name}` : 'Ticket unassigned')
    },
    onError: (error) => toast.error('Could not change the assignee', detailOf(error)),
  })
}

/**
 * Apply a workflow transition.
 *
 * Invalidates the transition list as well as the ticket: moving a ticket changes which moves are
 * legal next, so re-reading the backend's answer is the only way the buttons stay truthful.
 */
export function useTransitionTicket(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async ({ toStatus, comment }: { toStatus: string; comment?: string }) => {
      await ensureCsrfCookie()
      return ticketsApi.transition(id, toStatus, comment)
    },
    onSuccess: (ticket) => {
      queryClient.setQueryData<Ticket>(queryKeys.tickets.detail(id), ticket)
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.transitions(id) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.history(id) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.comments(id) })
      invalidateTicketCollections(queryClient)
      toast.success('Status changed', `Now ${ticket.status.replace(/_/g, ' ').toLowerCase()}.`)
    },
    onError: (error) => toast.error('Could not change the status', detailOf(error)),
  })
}

// -- Comments ---------------------------------------------------------------

export function useComments(ticketId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.tickets.comments(ticketId ?? ''),
    queryFn: () => ticketsApi.comments(ticketId as string),
    enabled: Boolean(ticketId),
  })
}

export function useAddComment(ticketId: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (body: string) => {
      await ensureCsrfCookie()
      return ticketsApi.addComment(ticketId, body)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.comments(ticketId) })
      // The ticket's comment counter in the list/detail header changes too.
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.detail(ticketId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.lists() })
    },
    onError: (error) => toast.error('Could not post the comment', detailOf(error)),
  })
}

export function useUpdateComment(ticketId: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async ({ commentId, body }: { commentId: string; body: string }) => {
      await ensureCsrfCookie()
      return ticketsApi.updateComment(commentId, body)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.comments(ticketId) })
      toast.success('Comment updated')
    },
    // `edit_window_closed` is a 400 whose explanation the user needs verbatim.
    onError: (error) => toast.error('Could not edit the comment', detailOf(error)),
  })
}

export function useDeleteComment(ticketId: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (commentId: string) => {
      await ensureCsrfCookie()
      return ticketsApi.deleteComment(commentId)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.comments(ticketId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.detail(ticketId) })
      toast.success('Comment deleted')
    },
    onError: (error) => toast.error('Could not delete the comment', detailOf(error)),
  })
}

// -- Attachments ------------------------------------------------------------

export function useAttachments(ticketId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.tickets.attachments(ticketId ?? ''),
    queryFn: () => ticketsApi.attachments(ticketId as string),
    enabled: Boolean(ticketId),
  })
}

export function useUploadAttachment(ticketId: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (file: File) => {
      await ensureCsrfCookie()
      return ticketsApi.uploadAttachment(ticketId, file)
    },
    onSuccess: (attachment) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.attachments(ticketId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.detail(ticketId) })
      toast.success('File uploaded', attachment.original_name)
    },
    // The validator's rejection (extension allow-list, size) arrives as a `file` field error.
    onError: (error) => {
      const fieldMessage = error instanceof ApiError ? error.fieldErrors('file')[0] : null
      toast.error('Could not upload the file', fieldMessage ?? detailOf(error))
    },
  })
}

export function useDeleteAttachment(ticketId: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (attachmentId: string) => {
      await ensureCsrfCookie()
      return ticketsApi.deleteAttachment(attachmentId)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.attachments(ticketId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.tickets.detail(ticketId) })
      toast.success('Attachment deleted')
    },
    onError: (error) => toast.error('Could not delete the attachment', detailOf(error)),
  })
}

function detailOf(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Please try again.'
}
