/** Shapes the managed paper routes serve: position state, entry evidence, funding rows, candidates and rules. */

export type Snapshot = {
  source: string
  precision: string
  observed_at: number | null
  received_at: number | null
  best_bid: number | null
  best_ask: number | null
  bid_levels: number
  ask_levels: number
}

export type Fill = {
  /** ``book_walk_parts`` sums an exit that filled across observations; each part keeps its own walk. */
  basis: 'book_walk' | 'reference_moved_by_book_cost' | 'book_walk_parts'
  fill_price: number
  quantity: number
  reference_price?: number
  cost_bps: number | null
  cost_usdc: number | null
  half_spread_bps: number | null
  depth_bps: number | null
  total_bps: number | null
  levels_taken?: [number, number][]
  levels_available?: number
  levels_within_bound?: number
  max_depth_bps?: number | null
  complete?: boolean
  unfilled?: number
  limited_by?: 'depth_bound' | 'displayed_levels' | null
  shortfall?: string | null
  parts?: number
  snapshot: Snapshot | null
}

/** One part of an exit: what a single observation's book took, with its own price, fee and book. */
export type ExitPart = {
  index: number
  at: number
  quantity: number
  fill_price: number
  fee_usdc: number
  gross_usdc: number
  remaining_after: number
  observation: Observation
  fill: Fill
}

export type StyleRules = {
  version: string
  style: string
  atr_interval: string
  atr_seconds: number
  atr_period: number
  stop_atr: number
  reward_risk: number
  min_target_pct: number
  max_hold_s: number
  trail_activate_r: number
  trail_atr: number
  /** How far past the touch a fill may walk; the rest of the size waits for another observation. */
  max_depth_bps?: number
}

export type QuoteObservation = { kind: 'quote'; observed_at: number; received_at: number; best_bid: number; best_ask: number; touch: number }
export type CandleObservation = {
  kind: 'candle'; interval_s: number; open_time: number; close_time: number
  open: number; high: number; low: number; close: number; received_at: number
}
export type Observation = QuoteObservation | CandleObservation

export type ExitRecord = {
  rule: string
  level: number | null
  trigger_price: number
  gap_fill: boolean
  path: string | null
  ambiguous_candle: boolean
  trigger_observation: Observation
  fill_observation: Observation
  fill_price: number
  at: number
  parts?: number
  /** A rule that fired at the same observation as a kill switch, kept beside it. */
  coincided_rule?: string
  kill_switch?: { operator: string; reason: string }
}

export type FundingSummary = {
  model: string
  accrued_usdc: number
  settled_hours: number
  expected_hours: number
  missing_hours: number[]
  through: number
  status: 'complete' | 'awaiting_rows'
}

export type FeeSchedule = { taker_fee: number; maker_fee: number; source: string; read_on: string }

export type PaperPosition = {
  version?: string
  status: string
  side: string
  style: string
  rules?: StyleRules
  atr?: number
  entry_time: number
  entry_price: number
  quantity?: number
  /** What is still held: an exit filled in part has already left the rest behind. */
  open_quantity?: number
  exit_parts?: ExitPart[]
  notional: number
  stop: number
  target: number
  expiry: number
  current_stop?: number
  current_stop_rule?: 'stop' | 'trailing_stop'
  trail?: { activate_price: number; distance: number; best: number | null; active: boolean; stop: number | null }
  fees?: { schedule: FeeSchedule; liquidity: string; rate: number; entry_usdc: number; exit_usdc: number | null; exit_estimate_usdc: number | null }
  slippage?: { model: string; entry: Fill; exit: Fill | null }
  funding?: FundingSummary
  gross_pnl_usdc?: number | null
  fees_usdc?: number
  funding_usdc?: number
  net_estimate_usdc: number | null
  last_quote_time: number
  observations: number
  observation_gap: boolean
  max_observation_gap_s: number
  pending_exit?: {
    rule: string; observation: Observation; unfilled: string | null
    parts?: number; remaining_quantity?: number; coincided_rule?: string; kill_switch?: { operator: string; reason: string }
  } | null
  exit?: ExitRecord | null
  exit_reason?: string
  exit_price?: number
  exit_time?: number
}

export type PaperRowData = { id: string; symbol: string; evidence_sha256: string; position_state: PaperPosition }
export type Portfolio = { positions: PaperRowData[]; worker: { last_tick: number | null; last_error: string | null }; note: string }

export type EvidenceRecord = { observed_at: number; received_at: number; age_s: number; id?: string | null } & Record<string, unknown>
export type EvidenceItem = {
  label: string
  source: string | null
  status: 'present' | 'missing'
  reason: string | null
  coverage: string | null
  records: EvidenceRecord[]
  newest_age_s: number | null
  excluded_count: number
  excluded: { reason: string; observed_at: unknown; received_at: unknown; id: unknown }[]
}
export type ExternalContext = {
  status: string; cutoff?: number; excluded?: number; events?: unknown[]; samples?: unknown[]
  coverage?: string; reason?: string; scoring_influence?: boolean
}
export type EvidenceDocument = {
  schema_version?: string
  entry_time?: number
  cutoff_rule?: string
  excluded_count?: number
  items?: Record<string, EvidenceItem>
  item_order?: string[]
  external_context?: Record<string, ExternalContext>
}
export type EvidenceResponse = { entry_evidence?: EvidenceDocument; evidence_sha256?: string; digest_verified?: boolean }

export type FundingRow = {
  settled_at: number; funding_rate: number; premium: number | null; side: string; quantity: number; price: number
  price_source: string; price_observed_at: number | null; payment_usdc: number; received_at: number; recorded_at: number
}
export type FundingRows = { rows: FundingRow[]; model: string; note: string }

export type Candidate = {
  id: string; symbol: string; timeframe: string; dir: string; direction: string; bias: number; quality: number
  snapshot_ts: string; expires_at: string | null; age_s: number; position_id: string | null; style_alignment: StyleAlignment
}
export type StyleAlignment = {
  policy: string; style: string; horizon: string | null; direction: string; expected_lean?: string; observed_lean?: string | null
  implied_move_pct?: number | null; minimum_move_pct?: number; measured_at?: string | null; measurement_age_s?: number | null
  eligible: boolean; reasons: string[]; checks: { code: string; passed: boolean }[]; meaning: string
}
export type RejectedCandidate = { id: string; symbol: string; dir: string; style_alignment: StyleAlignment }
export type Candidates = { universe: string[]; max_age_s: number; checked_at: number; candidates: Candidate[]; symbols_without_candidate: string[]; rejected_candidates: RejectedCandidate[]; style: string; style_policy: string }

export type RulesCatalog = {
  version: string
  styles: Record<string, StyleRules>
  common: { max_notional_usdc: number; max_planned_risk_usdc: number; max_opportunity_age_s: number; observation_gap_s: number }
  fees: FeeSchedule
  fill_model: string
  funding_model: string
  evidence_schema: string
}
