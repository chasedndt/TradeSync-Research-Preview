// Thesis editions, event reactions, the outlook, briefings and the Hermes link. Moved unchanged from types.ts, which re-exports this file.

import type { ThesisResponse } from './thesisTypes'

// === Thesis editions ===

export interface ThesisEdition {
  id: string
  edition: 'ny-premarket' | 'ny-midday' | 'session-handoff' | 'manual'
  generated_at: string
  symbols: string[]
  headline: string
  text: string
  narration: string
  verdicts: Record<string, string>
  media: Record<string, string>
  trigger: string
  schema_version: string
  theses?: Record<string, ThesisResponse>
  /** Empty object on editions made before the outlook existed. */
  outlook: MarketOutlook | Record<string, never>
  briefing: HermesBriefing | Record<string, never>
  reason: string
}

export interface EditionGeneration {
  running: boolean
  stage: string
  edition: string | null
  reason: string
  trigger: string | null
  started_at: string | null
  finished_at: string | null
  last_error: string | null
  last_id: string | null
}

export interface ThesisEditionsResponse {
  schema_version: 'thesis_editions_v2'
  editions: ThesisEdition[]
  generation: EditionGeneration
  schedule: { timezone: string; entries: string; enabled: boolean; next: { edition: string | null; at: string | null } }
}

export interface EventReactionHorizon {
  n: number
  median_abs_move_pct: number | null
  median_range_pct: number | null
  baseline_median_abs_move_pct: number | null
  baseline_days: number
  volatility_ratio: number | null
  up_share: number | null
  mean_move_pct: number | null
}

export interface OutlookArticle { title: string; url: string; domain: string; seen: string }

export interface OutlookKeyEvent {
  title: string
  country: string | null
  impact: string | null
  scheduled_at: string
  minutes_until: number
  source: string | null
  url: string | null
  forecast?: string | null
  previous?: string | null
  kind: string | null
  kind_label: string | null
  /** symbol -> horizon ("1h" | "4h" | "24h") -> measured reaction */
  reaction: Record<string, Record<string, EventReactionHorizon>>
  guidance: string[]
  articles: OutlookArticle[]
  /** Other titles for the same release at the same instant, merged into this event. */
  related_titles?: string[]
}

export interface MarketOutlook {
  schema_version: 'market_outlook_v1'
  generated_at: string
  breadth: {
    lean: 'bearish' | 'bullish' | 'mixed' | 'none'
    summary: string
    reads: { LONG: number; SHORT: number; NONE: number }
    regimes: Record<string, number>
    verdicts: Record<string, number>
    meaning: string
  }
  leads: {
    symbol: string
    direction: string | null
    regime: string | null
    verdict: string | null
    last: number | null
    low_24h: number | null
    high_24h: number | null
    invalidation: number | null
    coverage: number | null
  }[]
  key_events: OutlookKeyEvent[]
  notes: string[]
  reaction_method: { measure: string; baseline: string; window: Record<string, unknown>; caveat: string }
  /** Frozen BTC/ETH multi-horizon evidence on editions created by the integrated-story renderer. */
  horizon_context?: Record<string, { computed_at: Record<string, string>; outlook: import('./horizonTypes').HorizonOutlook; note: string }>
}

export interface HermesBriefing {
  status: 'ok' | 'refused' | 'unavailable' | 'not_configured'
  content?: string
  model?: string
  elapsed_ms?: number
  detail?: string
  receipt?: { content_digest?: string }
  authority?: string
  source?: string
}

export interface EventReactionsResponse {
  schema_version: 'event_reactions_v1'
  computed_at: string | null
  computing: boolean
  window: Record<string, unknown>
  errors: string[]
  kinds: Record<string, { label: string; source_url: string }>
  key_events: OutlookKeyEvent[]
  note: string
}

export interface HermesLinkStatus {
  status: 'live' | 'degraded' | 'offline' | 'checking' | 'not_configured'
  name: string
  url: string | null
  host: string | null
  port: number | null
  api: string
  version: string | null
  platform: string | null
  last_seen_at: string | null
  seconds_since_seen: number | null
  last_check_at: string | null
  latency_ms: number | null
  consecutive_failures: number
  last_error: string | null
  models: string[]
  models_ok: boolean | null
  models_error: string | null
  heartbeat_s: number
  availability_recent: number | null
  checks: { at: string; ok: boolean; latency_ms?: number; error?: string }[]
  watching_since: string | null
  gateway: {
    payload: {
      gateway_state?: string
      pid?: number
      code_version?: string
      active_agents?: number
      updated_at?: string
      platforms?: Record<string, { state: string; error_message?: string | null; updated_at?: string }>
    }
    source_updated_at: string | null
    snapshot_at: string
  } | null
  boundary: Record<string, boolean>
}
