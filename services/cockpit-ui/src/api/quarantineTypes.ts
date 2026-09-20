// Quarantined intake and its review. Moved unchanged from types.ts, which re-exports this file.

export interface QuarantineReason {
  code: string
  detail: string
}

export interface QuarantineItem {
  id: string
  source: string
  /** Whether it passed intake. Acceptance confers no authority. */
  accepted: boolean
  content_digest: string
  payload: Record<string, unknown>
  reasons: QuarantineReason[]
  observed_at: string | null
  received_at: string
  reviewed_by: string | null
  /** Null until an operator promotes it. Promotion is never automatic. */
  promoted_to: string | null
  /** What extraction made of it: the rule pass, and the harness pass if it was asked. */
  extraction?: {
    rule: { claims: number; reason: string } | null
    harness: { claims: number; reason: string } | null
  }
}

export interface QuarantineList {
  schema_version: string
  /** Always "none" — quarantined material carries no authority. */
  authority: string
  items: QuarantineItem[]
  note: string
}

export interface QuarantineReviewResult {
  id: string
  reviewed_by: string
  promoted: boolean
  blockers: QuarantineReason[]
  authority: string
  note: string
}
