import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { OpportunityBrief, OpportunityBriefList } from '../opportunityBriefTypes'

/** Compact briefs for one status, newest first, read from stored records. */
export function useOpportunityBriefs(status: string, limit = 100) {
  return useQuery({
    queryKey: ['opportunity-briefs', status, limit],
    queryFn: () => apiGet<OpportunityBriefList>(
      `/state/opportunity-briefs?status=${encodeURIComponent(status)}&limit=${limit}`,
    ),
    refetchInterval: 15_000,
    placeholderData: keepPreviousData,
    retry: 1,
  })
}

/** One full brief: entry conditions, plan, evidence, provenance and paper state. */
export function useOpportunityBrief(opportunityId: string | undefined) {
  return useQuery({
    queryKey: ['opportunity-brief', opportunityId],
    queryFn: () => apiGet<OpportunityBrief>(`/state/opportunity-briefs/${encodeURIComponent(opportunityId ?? '')}`),
    enabled: Boolean(opportunityId),
    refetchInterval: 15_000,
    retry: 1,
  })
}
