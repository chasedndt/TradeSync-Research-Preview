// The market thesis. Moved unchanged from types.ts, which re-exports this file.

import type { CalendarEvent } from './contextFeedTypes'

// === Thesis (slice 6: the SOP's minimum valid thesis) ===

export interface ThesisLine {
  text: string
  source: string
  captured_at_ms: number | null
  age_ms: number | null
}

export interface ThesisAnchors {
  source?: string
  bucket_s: number
  candles: number
  note?: string
  last_close?: number | null
  last_open?: number | null
  high_1h?: number; low_1h?: number; covered_1h?: boolean
  high_4h?: number; low_4h?: number; covered_4h?: boolean
  high_24h?: number; low_24h?: number; covered_24h?: boolean
}

export interface ThesisStackItem {
  feature_id: string
  score: number | null
  reads: 'LONG' | 'SHORT' | 'flat'
  quality: number | null
  standing: 'scoring' | 'context_only' | 'unknown'
  earned: boolean
  earned_by: string[]
  entries_with_reading: number | null
}

export interface ThesisResponse {
  schema_version: 'thesis_v1'
  symbol: string
  generated_at_ms: number
  visibility: 'private'
  verdict: 'NO TRADE' | 'PAPER READ ONLY'
  freshness: { source_status: Record<string, unknown>; observation_age_ms: number | null; stale: boolean; stale_after_ms: number }
  structure: {
    entry_regime: string
    trailing_return_pct: number | null
    lookback_minutes: number | null
    direction: 'LONG' | 'SHORT' | 'NONE'
    directional_score: number | null
    signal_evaluated_at_ms: number | null
  }
  anchors: ThesisAnchors
  derivatives: {
    feature_id: string
    label: string
    value: number | null
    unit: string | null
    observed_at_ms: number | null
    age_ms: number | null
    status: string
    scoring_allowed: boolean
  }[]
  confirmation_stack: ThesisStackItem[]
  sources: { earned: { source_id: string; source: string; earned_by: string[] }[]; measured: number; recording: number }
  invalidation: { level: number | null; rule: string; source?: string }
  no_trade_conditions: { code: string; active: boolean; detail: string }[]
  confidence: { evidence_coverage: number | null; meaning: string }
  skill_gate: { gate: 'OPEN' | 'CLOSED' | null; any_economic_edge: boolean }
  upcoming_events: CalendarEvent[]
  lines: ThesisLine[]
  text: string
  note: string
}
