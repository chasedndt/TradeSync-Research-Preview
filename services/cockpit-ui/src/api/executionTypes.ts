// Orders, positions, risk limits, preview and execution results. Moved unchanged from types.ts, which re-exports this file.

export interface ExecOrder {
  id: string
  decision_id: string
  venue: string
  status: string
  request: Record<string, unknown>
  response: Record<string, unknown>
  dry_run: boolean
}

export interface Position {
  venue: string
  symbol: string
  side: string
  size_usd: number
  entry_price: number
  mark_price: number
  pnl_usd: number
  leverage: number
  timestamp: string
}

export interface RiskLimitResponse {
  max_leverage: number
  min_quality: number
  max_open_positions: number
  min_size_usd: number
  max_event_age: number
  max_signal_age: number
  blacklist: string[]
  daily_notional_limit: number
  current_counters: {
    daily_notional_usage: number
    today_date: string
  }
}

export interface PreviewRequest {
  opportunity_id: string
  size_usd: number
  venue: string
}

export interface PreviewResponse {
  decision_id: string | null
  plan: Record<string, unknown>
  risk_verdict: {
    allowed: boolean
    reason: string
    checks: Record<string, boolean>
  }
  suggested_adjustments: Record<string, unknown> | null
}

export interface ExecuteRequest {
  decision_id: string
  confirm: boolean
}

export interface ExecutionResult {
  ok: boolean
  venue: string
  dry_run: boolean
  execution_enabled: boolean
  status: 'placed' | 'rejected' | 'error'
  order_id: string | null
  idempotency_key: string
  request_payload: Record<string, unknown>
  response_payload: Record<string, unknown>
  error: { code: string; message: string } | null
  ts: string
}

export interface ExecutionStatus {
  execution_enabled: string
  venues: VenueStatus[]
}

export interface VenueStatus {
  venue: string
  circuit_open: boolean | string
  fail_count?: number
  error?: string
}
