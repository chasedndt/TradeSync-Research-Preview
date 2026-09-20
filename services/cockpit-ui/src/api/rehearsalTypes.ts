// Paper rehearsal. Moved unchanged from types.ts, which re-exports this file.

// === Paper rehearsal ===

export interface RehearseRequest {
  opportunity_id: string
  size_usd: number
}

export interface SimulatedFill {
  direction: 'LONG' | 'SHORT'
  size_usd: number
  mark_price: number
  fill_price: number
  quantity: number
  half_spread_bps: number
  slippage_usd: number
  fee_usd: number
  entry_cost_usd: number
  /** Move needed in the called direction to cover entry costs alone. */
  breakeven_move_pct: number
  observed_at_ms: number
  fees: { taker_fee: number; maker_fee: number; source: string; read_on: string }
  simulated: true
  note: string
}

export interface RehearsalRecord {
  id: string
  opportunity_id: string
  symbol: string
  direction: 'LONG' | 'SHORT'
  size_usd: number
  status: 'rehearsed' | 'refused'
  plan: Record<string, unknown>
  risk_verdict: { allowed: boolean; reason_code: string; reason: string }
  fill: SimulatedFill | null
  market: { mark_price_usd?: number; spread_bps?: number; snapshot_ts?: number; snapshot_age_ms?: number | null }
  created_at: string
  note: string
}

export interface RehearseResponse {
  duplicate: boolean
  rehearsal: RehearsalRecord
}

export interface RehearsalListResponse {
  rehearsals: RehearsalRecord[]
  counts: { rehearsed: number; refused: number }
  execution_authority: false
  note: string
}
