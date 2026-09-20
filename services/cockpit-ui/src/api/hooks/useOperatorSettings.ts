import { useQuery } from '@tanstack/react-query'
import type { RulesCatalog } from '../../components/ledger/paper/paperTypes'
import { apiGet } from '../client'
import type { AccessPolicy, EnrolledPhones, PaperLimits, RetentionPolicy, SignerStatus } from '../operatorSettingsTypes'

/** What state-api enforces on a change. Shared by Operator access and the operator menu. */
export function useAccessPolicy() {
  return useQuery({
    queryKey: ['access-policy'],
    queryFn: () => apiGet<AccessPolicy>('/state/access-policy'),
    refetchInterval: 60_000,
    retry: false,
  })
}

/** What the isolated signer reports about itself; unreachable is its expected state. */
export function useSignerStatus() {
  return useQuery({
    queryKey: ['signer-status'],
    queryFn: () => apiGet<SignerStatus>('/state/execution/signer-status'),
    refetchInterval: 60_000,
    retry: false,
  })
}

/** The paper limits in force, with who last changed them, when and why. */
export function usePaperLimits() {
  return useQuery({
    queryKey: ['paper-limits'],
    queryFn: () => apiGet<PaperLimits>('/state/paper-limits'),
    refetchInterval: 60_000,
    retry: 1,
  })
}

/** The versioned paper lifecycle rules; the same query the paper entry form reads. */
export function usePaperRules() {
  return useQuery({
    queryKey: ['paper-rules'],
    queryFn: () => apiGet<RulesCatalog>('/state/paper-positions/rules'),
    staleTime: 3_600_000,
  })
}

/** How long each record is kept. Static facts, so read rarely. */
export function useRetentionPolicy() {
  return useQuery({
    queryKey: ['operator-retention'],
    queryFn: () => apiGet<RetentionPolicy>('/state/operator/retention'),
    staleTime: 300_000,
    retry: 1,
  })
}

/** Enrolled phones, listed only to a browser session holding the mobile control key (403 otherwise). */
export function useEnrolledPhones() {
  return useQuery({
    queryKey: ['operator-menu', 'enrolled-phones'],
    queryFn: () => apiGet<EnrolledPhones>('/state/mobile-alerts/devices'),
    refetchInterval: 60_000,
    retry: false,
  })
}
