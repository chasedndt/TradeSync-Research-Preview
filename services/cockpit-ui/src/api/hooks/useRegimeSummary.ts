import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { RegimeSummary } from '../regimeSummaryTypes'

/**
 * The regime for one market with the evidence behind it.
 *
 * The route answers 200 even when market-data cannot be read, because "the
 * source did not answer" is exactly what the panel needs to show, so a failed
 * reading here means the state API itself is unreachable.
 */
export function useRegimeSummary(symbol: string) {
  return useQuery({
    queryKey: ['regime-summary', symbol],
    queryFn: () => apiGet<RegimeSummary>(`/state/market/regime-summary?symbol=${encodeURIComponent(symbol)}`),
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
    retry: 1,
  })
}
