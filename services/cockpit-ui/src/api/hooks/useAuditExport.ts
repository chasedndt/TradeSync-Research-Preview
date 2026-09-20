import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { AuditExportReading } from '../activityTypes'

/**
 * The audit export as one JSON reading: decisions, approvals, orders and outcomes over the last `days`,
 * at most `rows` rows a section. It scans four tables on a database with a history of crash resets
 * under large scans, so it refreshes every five minutes and on request, never faster, and a remount
 * inside those five minutes shows the reading already held, with the time it was taken.
 */

const EVERY_FIVE_MINUTES = 300_000

export function useAuditExport(days: number, rows: number) {
  return useQuery({
    queryKey: ['audit-export', days, rows],
    queryFn: () => apiGet<AuditExportReading>(`/state/audit/export?days=${days}&rows=${rows}`),
    refetchInterval: EVERY_FIVE_MINUTES,
    staleTime: EVERY_FIVE_MINUTES,
  })
}
