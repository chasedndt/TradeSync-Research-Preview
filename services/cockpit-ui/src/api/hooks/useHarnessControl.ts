import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { HarnessChangeBody, HarnessControl } from '../harnessControlTypes'

const KEY = ['harness-control']
const moving = (control?: HarnessControl) => control?.host.status === 'pending' || control?.host.status === 'applying'

/** The agent harness kill switch; polled every few seconds while a stop or start is on its way to the gateway. */
export function useHarnessControl() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiGet<HarnessControl>('/state/agents/harness/control'),
    refetchInterval: (query) => (moving(query.state.data) ? 3_000 : 15_000),
    retry: 1,
  })
}

/** Stop or start the agent harness. The request names its operator and reason, and state-api records both. */
export function useHarnessChange() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: HarnessChangeBody) => apiPost<HarnessControl>('/state/agents/harness/control', body),
    onSuccess: (control) => qc.setQueryData(KEY, control),
    onSettled: () => Promise.all([['hermes-status'], ['harness-status']].map((queryKey) => qc.invalidateQueries({ queryKey }))),
  })
}
