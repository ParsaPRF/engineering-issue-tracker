/**
 * Team hooks: the directory search used by the member picker.
 *
 * `GET /auth/users/directory/` returns a plain array (not a page) and is restricted to admins and
 * project managers, who are exactly the roles that manage membership. It is disabled for an empty
 * term: an empty search would return the first 20 accounts of the installation, which is both
 * useless in a picker and an unnecessary enumeration surface.
 */

import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../../lib/queryClient'
import { authApi } from '../auth/api'
import type { UserSummary } from '../../types/api'

/** Query key for the directory search, shared with the auth feature so both read one cache entry. */
export function useDirectorySearch(search: string) {
  const term = search.trim()
  return useQuery<UserSummary[], unknown>({
    queryKey: queryKeys.directory(term),
    queryFn: () => authApi.directory(term),
    enabled: term.length > 0,
    staleTime: 30_000,
  })
}
