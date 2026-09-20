// The evidence timeline of an opportunity. Moved unchanged from types.ts, which re-exports this file.

export interface TimelineOutcome {
  horizon_minutes: number
  status: 'measured' | 'pending' | 'insufficient_candles'
  signed_return_pct: number | null
  forward_return_pct: number | null
  max_favourable_pct: number | null
  max_adverse_pct: number | null
}

export interface TimelineFeature {
  feature_id: string
  score: number
  data_quality: number
  block?: string
}

export interface TimelineEntry {
  opportunity_id: string
  signal_id: string | null
  symbol: string
  direction: string
  directional_score: number
  coverage_pct: number
  opened_at: string
  signal_at: string | null
  /** Digests pin the exact configuration, so a replay reproduces it exactly. */
  catalog_version: string | null
  catalog_digest: string | null
  rulebook_version: string | null
  rulebook_digest: string | null
  evidence_digest: string | null
  contributing_features: TimelineFeature[]
  missing_blocks: string[]
  paper_risk_multiplier: number | null
  outcomes: TimelineOutcome[]
}

export interface EvidenceTimeline {
  schema_version: string
  symbol: string
  entries: TimelineEntry[]
  note: string
}
