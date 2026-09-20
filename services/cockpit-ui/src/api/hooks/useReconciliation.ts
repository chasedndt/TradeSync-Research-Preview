import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { ExecutionReconciliation, ReconciliationViews, RegimeFitReading, ThesisAdherenceReading } from '../reconciliationTypes'

/**
 * Reconciliation and outcome-measure readings. Every one of them scans a table over a window on a
 * database with a history of crash resets under large scans, so they refresh every five minutes and
 * on request, never faster.
 */

const EVERY_FIVE_MINUTES = 300_000

export function useReconciliationViews(hours: number) {
  return useQuery({
    queryKey: ['reconciliation-views', hours],
    queryFn: () => apiGet<ReconciliationViews>(`/state/reconciliation/views?hours=${hours}`),
    refetchInterval: EVERY_FIVE_MINUTES,
  })
}

export function useExecutionReconciliation(hours: number) {
  return useQuery({
    queryKey: ['execution-reconciliation', hours],
    queryFn: () => apiGet<ExecutionReconciliation>(`/state/execution/reconciliation?hours=${hours}`),
    refetchInterval: EVERY_FIVE_MINUTES,
  })
}

export function useThesisAdherence() {
  return useQuery({
    queryKey: ['thesis-adherence'],
    queryFn: () => apiGet<ThesisAdherenceReading>('/state/outcomes/thesis-adherence'),
    refetchInterval: EVERY_FIVE_MINUTES,
  })
}

export function useRegimeFit(hours: number) {
  return useQuery({
    queryKey: ['regime-fit', hours],
    queryFn: () => apiGet<RegimeFitReading>(`/state/outcomes/regime-fit?hours=${hours}`),
    refetchInterval: EVERY_FIVE_MINUTES,
  })
}
