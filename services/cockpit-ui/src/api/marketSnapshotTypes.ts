// The market-data snapshot: price, funding, open interest, liquidations, book, volume, regime, alerts and status. Moved unchanged from types.ts, which re-exports this file.

// === Market Data Types (Phase 3B) ===

export type MetricStatus = 'REAL' | 'PROXY' | 'UNAVAILABLE' | 'STALE'

export interface MetricAvailability {
  metric: string
  status: MetricStatus
  source?: string
  last_updated?: number
  note?: string
}

export interface FundingHorizons {
  now: number
  h8: number
  h24: number
  d3: number
  d7: number
}

export interface FundingData {
  horizons: FundingHorizons
  annualized_24h: number
  regime: string
  source: {
    provider: string
    endpoint: string
    raw_rate: number
  }
}

export interface HorizonValue {
  value: number
  delta_pct: number
  delta_usd: number
}

export interface OpenInterestData {
  horizons: Record<string, HorizonValue>
  current_usd: number
  regime: string
}

export interface LiquidationWindow {
  longs_usd: number
  shorts_usd: number
  total_usd: number
  dominant_side: string
}

export interface LiquidationData {
  horizons: Record<string, LiquidationWindow>
  source_note?: string
  method: string
}

export interface OrderbookData {
  spread_bps: number
  spread_usd: number
  depth: {
    bid_1pct_usd: number
    ask_1pct_usd: number
    bid_2pct_usd: number
    ask_2pct_usd: number
  }
  imbalance_1pct: number
  best_bid: number
  best_ask: number
  mid_price: number
  book_age_ms: number
}

export interface VolumeData {
  horizons: Record<string, number>
  cvd?: Record<string, number>
  cvd_method?: string
  avg_7d_daily: number
  regime: string
}

export interface RegimeSummary {
  funding: string
  oi: string
  volume: string
  trend: string
  market_condition: string
  confidence: string
  confidence_note?: string
}

export interface PriceData {
  mark_price_usd: number
  oracle_price_usd: number
  oracle_premium_bps: number
  /** Venue-published previous-day reference; null when Hyperliquid omits it. */
  prev_day_price_usd?: number | null
  /** Derived from mark and prev_day only. Null means unavailable, not zero. */
  change_24h_pct?: number | null
}

export interface MarketSnapshot {
  venue: string
  symbol: string
  ts: number
  /**
   * Time since the venue was last observed for this symbol — liveness.
   * Distinct from data_age_ms, the age of the oldest metric inside the
   * snapshot — completeness. Judge "is the feed alive" on this one.
   */
  snapshot_age_ms?: number | null
  data_age_ms: number
  available_metrics: MetricAvailability[]
  price?: PriceData
  funding?: FundingData
  oi?: OpenInterestData
  liquidations?: LiquidationData
  volume?: VolumeData
  orderbook?: OrderbookData
  regimes: RegimeSummary
  sources: Array<{
    provider: string
    endpoint: string
    fetched_at: number
    metrics_provided: string[]
  }>
}

export interface MarketAlert {
  id: string
  venue: string
  symbol: string
  ts: number
  alert_type: string
  metric: string
  previous_value?: string
  new_value: string
  context: Record<string, unknown>
}

export interface MarketDataStatus {
  status?: string
  providers: Array<{
    venue: string
    enabled: boolean
    metrics: string[]
  }>
  symbols: string[]
  rate_limiters?: Record<string, unknown>
}
