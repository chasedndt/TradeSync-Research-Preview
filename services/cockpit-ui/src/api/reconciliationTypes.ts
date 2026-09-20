// === Reconciliation views (GET /state/reconciliation/views) ===

export interface ReconciliationFinding {
  kind: string
  subject_id: string | null
  detail: string
  observed: Record<string, unknown>
}

/** One comparison: what it compared, over what window, how many records it examined and what it found. */
export interface ReconciliationView {
  name: string
  compared: string
  window: string
  /** Zero means nothing was compared, which is not the same result as a clean comparison. */
  considered: number
  clean: boolean
  findings: ReconciliationFinding[]
  /** Counterparts that simply predate the window; never findings. */
  outside_window: string[]
  summary: string
}

export interface ReconciliationViews {
  schema_version: 'reconciliation_views_v1'
  views: ReconciliationView[]
  findings: number
  records_compared: number
  clean: boolean
  summary: string
  note: string
  generated_at: string
  window: { hours: number; from: string; to: string }
  row_cap_per_read: number
  horizons_minutes: number[]
  authority: 'read_only'
  beside: string
}

// === Execution reconciliation (GET /state/execution/reconciliation), which predates the views ===

export interface ExecutionDivergence {
  kind: string
  decision_id: string | null
  order_id: string | null
  field: string | null
  expected: unknown
  actual: unknown
  detail: string
}

/** Reports no time of its own: the Cockpit states when it received the reading. */
export interface ExecutionReconciliation {
  window_hours: number
  decisions: number
  orders: number
  matched: number
  divergences: ExecutionDivergence[]
  orders_outside_window: string[]
  clean: boolean
  summary: string
  paper_mode: boolean
  execution_gate_open: boolean
  note: string
}

// === Outcome metrics ===

export type CheckVerdict = 'pass' | 'fail' | 'absent'

export interface AdherenceCheck {
  name: string
  verdict: CheckVerdict
  detail: string
  observed: number | null
  allowed: number | null
}

export interface PositionAdherence {
  position_id: string
  symbol: string
  opened_at: string | null
  updated_at: string | null
  /** Null when no check could be judged; never zero for an absence. */
  adherence: number | null
  passed: number
  failed: number
  abstained: number
  checks_judged: number
  checks: AdherenceCheck[]
  departures: string[]
  reason: string | null
  basis: string
}

export interface AdherenceSummary {
  positions: number
  positions_scored: number
  unscored: number
  mean_adherence: number | null
  checks_passed: number
  checks_failed: number
  checks_abstained: number
  by_check: Record<string, Record<CheckVerdict, number>>
  note: string
}

export interface ThesisAdherenceReading {
  generated_at: string
  positions_considered: number
  limit: number
  positions: PositionAdherence[]
  summary: AdherenceSummary
  authority: 'read_only'
}

export type RegimeFitVerdict =
  | 'fit' | 'misfit' | 'undeclared' | 'unlabelled' | 'digest_mismatch' | 'rulebook_altered' | 'undirected' | 'no_rulebook'

export interface RegimeFitSummary {
  calls: number
  judged: number
  fit: number
  misfit: number
  regime_fit_rate: number | null
  abstained: number
  abstained_by_reason: Partial<Record<RegimeFitVerdict, number>>
  note: string
}

export interface RegimeFitReading {
  generated_at: string
  window: { hours: number; from: string; to: string }
  calls_considered: number
  rulebooks_held: number
  summary: RegimeFitSummary
  authority: 'read_only'
}
