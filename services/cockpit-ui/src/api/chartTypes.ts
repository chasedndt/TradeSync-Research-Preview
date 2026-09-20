// Candles, chart context series and order-book depth. Moved unchanged from types.ts, which re-exports this file.

export interface Candle {
  /** UNIX seconds, as the charting library expects. */
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface CandleResponse {
  venue: string
  symbol: string
  interval: string
  requested: number
  count: number
  candles: Candle[]
  /** Always "display_only" — candles are not catalog features. */
  authority: string
}

/** One value collapsed onto a candle open. */
export interface ContextPoint {
  /** UNIX seconds, aligned to the candle open. */
  time: number
  value: number
  /** How many raw samples fell in this bucket. */
  samples: number
}

/**
 * How much of the chart window a series actually covers.
 *
 * Reported rather than inferred: a line that stops has either run out of
 * recording or run into a collection gap, and those are different problems.
 */
export interface ContextCoverage {
  candles: number
  covered: number
  coverage_pct: number
  first_time: number | null
  last_time: number | null
}

export interface ContextSeries {
  series: ContextPoint[]
  unit: string
  source: string
  coverage: ContextCoverage
  /** Funding only: it is published hourly whatever the chart interval. */
  native_period_s?: number
  /** Open interest only: states why the series cannot reach further back. */
  limit_note?: string
}

export interface MarketContextResponse {
  venue: string
  symbol: string
  interval: string
  bucket_s: number
  funding: ContextSeries
  open_interest: ContextSeries
  /** Always "display_only". */
  authority: string
}

export interface DepthLevel {
  price: number
  size: number
  notional_usd: number
  /** Running notional outward from the touch: the cost to sweep to here. */
  cumulative_usd: number
  orders: number
}

/** A level holding an outsized share of its own side's visible notional. */
export interface RestingWall {
  side: 'bid' | 'ask'
  price: number
  notional_usd: number
  share_of_side: number
}

export interface DepthResponse {
  venue: string
  symbol: string
  poll_ts: number
  best_bid: number
  best_ask: number
  mid_price: number
  spread_bps: number
  imbalance_1pct: number
  depth: {
    bid_1pct_usd: number
    ask_1pct_usd: number
    bid_2pct_usd: number
    ask_2pct_usd: number
  }
  bids: DepthLevel[]
  asks: DepthLevel[]
  walls: RestingWall[]
  /** Always "display_only". */
  authority: string
}
