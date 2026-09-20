/**
 * The regime summary served by /state/market/regime-summary.
 *
 * Every figure here is calculated by `tradesync_core.regime_summary` and read
 * as it arrives. The Cockpit reproduces none of it: no threshold, no share and
 * no confidence level is recomputed in TypeScript.
 */

export type ConfidenceLevel = 'high' | 'medium' | 'low'

/** One required input behind the regime: what it read, where from, how old, and whether it counted. */
export interface RegimeComponent {
  input: string
  label: string
  regime: string
  /** REAL, DERIVED, PROXY, STALE, UNAVAILABLE or NOT_READ. */
  status: string
  /** Present in the reading at all; a proxy is present without being usable. */
  present: boolean
  /** The classifier was allowed to classify from it. */
  usable: boolean
  stale: boolean
  source: string | null
  detail: string | null
  observed_at_ms: number | null
  age_ms: number | null
  /** Why it could not be classified from; null when it could. */
  reason: string | null
}

export interface RegimeConflict {
  inputs: string[]
  detail: string
}

export interface RegimeMissingInput {
  input: string
  label: string
  status: string
  reason: string | null
}

export interface RegimeTransition {
  from: string
  to: string
  at_ms: number | null
  opportunity_id: string | null
  trailing_return_pct: number | null
}

export interface RegimeHeld {
  regime: string
  readings: number
  since_ms: number | null
  trailing_return_pct: number | null
  basis: string
}

export interface RegimeSummary {
  schema_version: 'regime_summary_v1'
  venue: string
  symbol: string
  /** When this reading was taken. */
  read_at_ms: number
  /** When the market itself was last read. */
  observed_at_ms: number | null
  snapshot_age_ms: number | null
  data_age_ms: number | null
  /** False when market-data could not be read at all. */
  source_read: boolean
  current: {
    condition: string
    label: string
    known: boolean
    trend: string
    trend_basis: string
  }
  confidence: {
    level: ConfidenceLevel
    usable_inputs: number
    required_inputs: number
    share_usable: number
    reported_by_market_data: string | null
    reported_note: string | null
    basis: string
  }
  components: RegimeComponent[]
  conflicts: RegimeConflict[]
  /** Every input the classifier could not use, each with the reason. Never empty while the condition is unknown. */
  missing_inputs: RegimeMissingInput[]
  /** Every reason confidence is not higher. Never empty while the condition is unknown. */
  why_not_higher: string[]
  at_highest_confidence: boolean
  history: {
    held: RegimeHeld | null
    transitions: RegimeTransition[]
    source: string
    readings: number
  }
  authority: string
  note: string
}
