/**
 * Project hooks.
 *
 * Membership and component mutations invalidate the project and every project list, because
 * `member_count` / `member_count`-style counters are computed server-side and would otherwise go
 * stale in the table.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, ensureCsrfCookie } from '../../lib/http'
import { queryKeys } from '../../lib/queryClient'
import { useToast } from '../../components/toast/ToastProvider'
import {
  projectsApi,
  type ComponentCreatePayload,
  type ComponentUpdatePayload,
  type ProjectCreatePayload,
  type ProjectListParams,
  type ProjectUpdatePayload,
} from './api'
import type { ProjectRole } from '../../types/api'

export function useProjects(params: ProjectListParams) {
  return useQuery({
    queryKey: queryKeys.projects.list(params),
    queryFn: () => projectsApi.list(params),
  })
}

export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.projects.detail(id ?? ''),
    queryFn: () => projectsApi.detail(id as string),
    enabled: Boolean(id),
  })
}

export function useProjectMembers(id: string | undefined, includeInactive = false) {
  return useQuery({
    queryKey: [...queryKeys.projects.members(id ?? ''), includeInactive] as const,
    queryFn: () => projectsApi.members(id as string, includeInactive),
    enabled: Boolean(id),
  })
}

export function useProjectComponents(id: string | undefined, includeInactive = false) {
  return useQuery({
    queryKey: [...queryKeys.projects.components(id ?? ''), includeInactive] as const,
    queryFn: () => projectsApi.components(id as string, includeInactive),
    enabled: Boolean(id),
  })
}

export function useProjectStats(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.projects.stats(id ?? ''),
    queryFn: () => projectsApi.stats(id as string),
    enabled: Boolean(id),
  })
}

function invalidateProjects(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: queryKeys.projects.all })
  // The dashboard's per-project table and the project filter both read project counters.
  void queryClient.invalidateQueries({ queryKey: ['reports'] })
}

export function useCreateProject() {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (payload: ProjectCreatePayload) => {
      await ensureCsrfCookie()
      return projectsApi.create(payload)
    },
    onSuccess: (project) => {
      invalidateProjects(queryClient)
      toast.success('Project created', `${project.key} — ${project.name}`)
    },
    onError: (error) => toast.error('Could not create the project', detailOf(error)),
  })
}

export function useUpdateProject(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (payload: ProjectUpdatePayload) => {
      await ensureCsrfCookie()
      return projectsApi.update(id, payload)
    },
    onSuccess: () => {
      invalidateProjects(queryClient)
      toast.success('Project updated')
    },
    onError: (error) => toast.error('Could not update the project', detailOf(error)),
  })
}

export function useArchiveProject(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (restore: boolean) => {
      await ensureCsrfCookie()
      return restore ? projectsApi.restore(id) : projectsApi.archive(id)
    },
    onSuccess: (project) => {
      invalidateProjects(queryClient)
      toast.success(project.status === 'ARCHIVED' ? 'Project archived' : 'Project restored', project.name)
    },
    onError: (error) => toast.error('Could not change the project status', detailOf(error)),
  })
}

export function useAddMember(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: ProjectRole }) => {
      await ensureCsrfCookie()
      return projectsApi.addMember(id, { user: userId, role })
    },
    onSuccess: (membership) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects.members(id) })
      invalidateProjects(queryClient)
      toast.success('Member added', `${membership.user_name} as ${membership.role.toLowerCase()}.`)
    },
    onError: (error) => toast.error('Could not add the member', detailOf(error)),
  })
}

export function useUpdateMemberRole(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async ({ membershipId, role }: { membershipId: string; role: ProjectRole }) => {
      await ensureCsrfCookie()
      return projectsApi.updateMemberRole(id, membershipId, role)
    },
    onSuccess: (membership) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects.members(id) })
      toast.success('Role updated', `${membership.user_name} is now ${membership.role.toLowerCase()}.`)
    },
    onError: (error) => toast.error('Could not change the role', detailOf(error)),
  })
}

export function useRemoveMember(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (membershipId: string) => {
      await ensureCsrfCookie()
      return projectsApi.removeMember(id, membershipId)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects.members(id) })
      invalidateProjects(queryClient)
      toast.success('Member removed')
    },
    onError: (error) => toast.error('Could not remove the member', detailOf(error)),
  })
}

export function useCreateComponent(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (payload: ComponentCreatePayload) => {
      await ensureCsrfCookie()
      return projectsApi.createComponent(id, payload)
    },
    onSuccess: (component) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects.components(id) })
      toast.success('Component created', component.name)
    },
    onError: (error) => toast.error('Could not create the component', detailOf(error)),
  })
}

export function useUpdateComponent(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async ({ componentId, payload }: { componentId: string; payload: ComponentUpdatePayload }) => {
      await ensureCsrfCookie()
      return projectsApi.updateComponent(componentId, payload)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects.components(id) })
      toast.success('Component updated')
    },
    onError: (error) => toast.error('Could not update the component', detailOf(error)),
  })
}

export function useDeactivateComponent(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: async (componentId: string) => {
      await ensureCsrfCookie()
      return projectsApi.deactivateComponent(componentId)
    },
    onSuccess: (component) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects.components(id) })
      toast.success('Component deactivated', component.name)
    },
    onError: (error) => toast.error('Could not deactivate the component', detailOf(error)),
  })
}

function detailOf(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Please try again.'
}
