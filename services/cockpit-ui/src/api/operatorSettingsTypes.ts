/**
 * The operator-facing readings behind Settings and the operator menu. Kept apart
 * from api/types.ts, which other branches edit.
 */

import type { TokenState } from '../components/settings/operatorTokenText'
import type { LimitValues } from './paperRiskTypes'

/** GET /state/access-policy: what state-api enforces on a change. It never carries the token. */
export interface AccessPolicy {
  operator_token: TokenState
  origin_check: 'enforced' | 'disabled'
}

/** GET /state/execution/signer-status: what the isolated signer reports, or that it could not be reached. */
export interface SignerStatus {
  reachable: boolean
  available?: boolean
  status?: string
  detail?: string
}

/** GET /state/paper-limits. */
export interface PaperLimits {
  limits: LimitValues
  operator: string
  reason: string
  updated_at: string | null
  authority: string
  note: string
}

export interface RetentionWindow {
  table: string
  what: string
  kept_days: number
  full_detail_days: number | null
  downsampled_to_minutes: number | null
  run_by: string
  override: string | null
  detail: string
}

/** GET /state/operator/retention, read from the code that deletes each record. */
export interface RetentionPolicy {
  schema_version: 'retention_policy_v1'
  windows: RetentionWindow[]
  kept: string
  not_retention: Record<string, string>
  note: string
}

/** The two fields the operator menu reads from GET /state/mobile-alerts/devices. */
export interface EnrolledPhones {
  devices: Array<{ id: string; enabled: boolean }>
}
