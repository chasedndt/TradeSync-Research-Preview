/**
 * Opportunity briefs served by /state/opportunity-briefs.
 *
 * Assembled by `tradesync_core.opportunity_brief` from stored records only: the
 * opportunity and the decision stored with it, the regime recorded before its
 * entry, the paper position opened from it and the plan frozen at that entry.
 * The Cockpit derives none of it. Kept apart from api/types.ts, which other
 * branches edit.
 */

export type RegimeFit = 'with' | 'against' | 'flat' | 'unlabelled'

export interface BriefCondition {
  code: string
  label: string
  measured: number | null
  required: number | null
  comparator: '>=' | '<='
  /** "share" (0 to 1), "score" or "ms". */
  unit: string
  /** The gate's comparison restated on the stored values; null when either value is missing. */
  met: boolean | null
  basis: string
}

export interface BriefEntry {
  schema: 'paper_signal_v1' | 'legacy'
  admitted: boolean | null
  conditions: BriefCondition[]
  conditions_met: number
  conditions_checked: number
  rejection_reasons: Array<{ code: string; detail?: string }>
  policy_note: string | null
  detail: string
}

export interface BriefRegimeFit {
  fit: RegimeFit
  regime: string | null
  trailing_return_pct: number | null
  lookback_minutes: number | null
  computed_at_s: number | null
  reason: string | null
  detail: string
  basis: string
}

export interface StyleRulesAtEntry {
  stop_atr: number
  atr_interval: string
  reward_risk: number
  min_target_pct: number
  max_hold_s: number
}

/** No paper position was opened, so no level was ever set. */
export interface BriefPlanNone {
  status: 'none'
  detail: string
  rules_at_entry: {
    version: string
    styles: Record<string, StyleRulesAtEntry>
    max_planned_risk_usdc: number
    min_net_reward_risk: number
    max_opportunity_age_s: number
  }
}

/** The plan frozen when a paper position opened. */
export interface BriefPlanFixed {
  status: string
  detail: string
  position_id: string
  opened_at_s: number | null
  entry_evidence_sha256: string | null
  side: string | null
  style: string | null
  rules_version: string | null
  entry_price: number | null
  quantity: number | null
  notional_usdc: number | null
  invalidation: { level: number | null; rule: string; current_stop: number | null; current_stop_rule: string | null }
  stop: number | null
  stop_distance: number | null
  atr: number | null
  targets: Array<{ level: number | null; basis: string }>
  expiry_s: number | null
  estimated_risk_usdc: number | null
  estimated_reward_usdc: number | null
  cost_budget_usdc: number | null
  net_reward_risk: number | null
  risk_basis: string
  exit: { rule: string | null; price: number | null; at_s: number | null; net_estimate_usdc: number | null } | null
}

export type BriefPlan = BriefPlanNone | BriefPlanFixed

export interface BriefFeature {
  feature_id: string
  block?: string | null
  score?: number | null
  data_quality?: number | null
  provenance?: string | null
  observed_at_ms?: number | null
}

export interface BriefState {
  label: string
  detail: string
  /** "none", "open", "closed" or "unknown". */
  position: string
  entries_paused: boolean | null
  entry_refusal: string | null
  execution_enabled: boolean
  execution_authority: false
  mode: string
}

export interface BriefConfig {
  id: string | null
  version: string | null
  digest: string | null
}

export interface OpportunityBrief {
  schema_version: 'opportunity_brief_v1'
  id: string
  symbol: string
  timeframe: string
  side: string
  status: string
  opened_at_s: number | null
  expires_at_s: number | null
  read_at_s: number
  age_s: number | null
  stored_scores: { directional_score: number | null; evidence_coverage_pct: number | null; basis: string }
  regime_fit: BriefRegimeFit
  entry: BriefEntry
  plan: BriefPlan
  evidence: {
    contributing_features: BriefFeature[]
    directional_contributors: Array<{ feature_id: string; score?: number | null; quality?: number | null }>
    missing_blocks: string[]
    risk_caps_applied: Array<{ flag: string; cap: number; known: boolean }>
    paper_risk_multiplier: number | null
  }
  provenance: {
    signal_id: string | null
    scorer: string | null
    decision_schema: string | null
    evidence_digest: string | null
    evaluated_at_ms: number | null
    rulebook: BriefConfig
    catalog: BriefConfig
    entry_evidence_sha256: string | null
    entry_reference_price: number | null
    entry_reference_basis: string
  }
  state: BriefState
  authority: 'paper_only'
  note: string
}

/** The list form: what a card shows. The full brief is one request away. */
export interface OpportunityBriefCard {
  schema_version: 'opportunity_brief_v1'
  id: string
  symbol: string
  timeframe: string
  side: string
  status: string
  opened_at_s: number | null
  expires_at_s: number | null
  read_at_s: number
  age_s: number | null
  stored_scores: OpportunityBrief['stored_scores']
  authority: 'paper_only'
  regime_fit: Pick<BriefRegimeFit, 'fit' | 'regime' | 'detail'>
  entry: Pick<BriefEntry, 'schema' | 'admitted' | 'conditions_met' | 'conditions_checked'>
  plan: {
    status: string
    detail: string
    stop: number | null
    targets: BriefPlanFixed['targets'] | null
    invalidation: BriefPlanFixed['invalidation'] | null
    estimated_risk_usdc: number | null
    estimated_reward_usdc: number | null
    net_reward_risk: number | null
    expiry_s: number | null
  }
  provenance: Pick<OpportunityBrief['provenance'], 'signal_id' | 'evidence_digest' | 'evaluated_at_ms'>
  state: Pick<BriefState, 'label' | 'detail' | 'position' | 'entries_paused' | 'execution_enabled' | 'mode'>
}

export interface OpportunityBriefList {
  schema_version: 'opportunity_briefs_v1'
  read_at_s: number
  status: string
  briefs: OpportunityBriefCard[]
  authority: string
  note: string
}
