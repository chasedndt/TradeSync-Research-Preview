// Opportunities, signals, events and decisions, and the evidence bundle that joins them. Moved unchanged from types.ts, which re-exports this file.

import type { ExecOrder } from './executionTypes'

export interface Opportunity {
  id: string
  symbol: string
  timeframe: string
  bias: number
  quality: number
  dir: string
  status: string
  snapshot_ts: string
  /** When the opportunity stops being live; the API reports status "expired" after it. */
  expires_at?: string | null
  links: Record<string, unknown>
}

export interface Signal {
  id: string
  created_at: string
  agent: string
  symbol: string
  timeframe: string
  kind: string
  confidence: number
  dir: string
  features: Record<string, unknown>
}

export interface Event {
  id: string
  ts: string
  source: string
  kind: string
  symbol: string
  timeframe: string
  payload: Record<string, unknown>
}

export interface Decision {
  id: string
  opportunity_id?: string
  venue: string
  requested: Record<string, unknown>
  risk: Record<string, unknown>
}

export interface EvidenceResponse {
  opportunity: Opportunity | null
  signals: Signal[]
  events: Event[]
  decisions: Decision[]
  exec_orders: ExecOrder[]
}
