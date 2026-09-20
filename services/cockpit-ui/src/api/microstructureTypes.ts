// Microstructure, execution risk, score breakdown and confluence. Moved unchanged from types.ts, which re-exports this file.

import type { MarketSnapshot } from './marketSnapshotTypes'
import type { Opportunity } from './opportunityTypes'

// === Phase 3C: Microstructure Types ===

export interface BookHeatmapLevel {
  price: number
  side: 'bid' | 'ask'
  size_usd: number
}

export interface MicrostructureData {
  spread_bps: number
  mid_price: number
  depth_usd: Record<string, number>  // Keys: "10bp", "25bp", "50bp"
  impact_est_bps: Record<string, number>  // Keys: "1000", "5000", "10000" (USD sizes)
  liquidity_score: number
  book_heatmap: BookHeatmapLevel[]
}

export interface ExecutionRisk {
  spread_bps: number
  impact_est_bps_5k: number
  depth_25bp: number
  liquidity_score: number
  flags: string[]
}

export interface ScoreBreakdown {
  alpha: number
  microstructure_penalty: number
  exposure_penalty: number
  regime_bonus: number
  final_score: number
  notes: string[]
}

export interface Confluence {
  score_breakdown: ScoreBreakdown
  execution_risk: ExecutionRisk
  warnings: string[]
}

// Extended Opportunity with Phase 3C confluence data
export interface OpportunityWithConfluence extends Opportunity {
  confluence?: Confluence
}

// Extended MarketSnapshot with Phase 3C microstructure
export interface MarketSnapshotWithMicrostructure extends MarketSnapshot {
  microstructure?: MicrostructureData
}
