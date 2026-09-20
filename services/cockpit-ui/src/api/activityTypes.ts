// === Audit export (GET /state/audit/export), read by the Activity & Evidence page ===
//
// Rows arrive cut down to the columns tradesync_core.audit_export declares, with every
// free-form payload scrubbed by key. Times are ISO strings exactly as state-api wrote them.

export type AuditSectionName = 'decisions' | 'approvals' | 'orders' | 'outcomes'

/** A JSON payload as stored. A field under a secret-looking key reads "[redacted]". */
export type StoredPayload = Record<string, unknown>

export interface DecisionRow {
  id: string
  created_at: string | null
  opportunity_id: string | null
  venue: string | null
  /** The plan the preview produced: action, symbol, size_usd, venue, slippage_tolerance. */
  requested: StoredPayload | null
  /** The risk verdict stored with the decision: allowed, reason_code, reason, suggested_adjustment. */
  risk: StoredPayload | null
}

export interface ApprovalRow {
  envelope_id: string
  approval_id: string
  approval_decision_id: string
  approval_digest: string
  approved_at: string | null
  candidate_id: string
  candidate_hash: string
  created_at: string | null
  /** Null until a paper evaluation consumes the approval. */
  consumed_at: string | null
  consumed_by: string | null
}

export interface OrderRow {
  id: string
  created_at: string | null
  decision_id: string | null
  venue: string | null
  status: string | null
  /** True when the order was recorded in paper mode and not sent to a venue. */
  dry_run: boolean | null
  txid: string | null
  request: StoredPayload | null
  /** The execution result as the boundary returned it, including any error. */
  response: StoredPayload | null
}

export interface OutcomeRow {
  opportunity_id: string
  symbol: string
  direction: string
  horizon_minutes: number
  /** measured, pending or insufficient_candles. */
  status: string
  entry_price: number | null
  exit_price: number | null
  /** Percent, as measured by state-api; null unless measured. */
  forward_return_pct: number | null
  signed_return_pct: number | null
  max_favourable_pct: number | null
  max_adverse_pct: number | null
  candles_used: number
  reason: string
  opened_at: string | null
  measured_at: string | null
  evidence_digest: string | null
}

export interface AuditSection<Row> {
  name: AuditSectionName
  columns: string[]
  rows: Row[]
  row_count: number
  /** The read takes one row past the cap to detect truncation, so this is never a total for the window. */
  rows_available_in_window: number
  truncated: boolean
  row_cap: number
  redacted_fields: number
  stored_digests: string[]
  /** Over these rows only; a different cap gives a different digest. */
  content_digest: string
}

export interface AuditExportReading {
  schema_version: 'audit_export_v1'
  generated_at: string
  window: { days: number; from: string; to: string }
  bounds: { max_rows_per_section: number; max_window_days: number; note: string }
  sections: {
    decisions: AuditSection<DecisionRow>
    approvals: AuditSection<ApprovalRow>
    orders: AuditSection<OrderRow>
    outcomes: AuditSection<OutcomeRow>
  }
  row_count: number
  truncated: boolean
  redacted_fields: number
  content_digest: string
  verification: string
  note: string
}
