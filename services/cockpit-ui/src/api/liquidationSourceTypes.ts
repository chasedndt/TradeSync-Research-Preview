/**
 * The `derived` context market-data attaches to every snapshot.
 *
 * `liquidity_context.attach` writes these onto the snapshot payload before it
 * is stored, and the snapshot is served as the stored dictionary, so they have
 * always reached the Cockpit — they were simply never declared, which is why
 * the liquidation panels could not tell an inference apart from a reading.
 *
 * A part that is stale or missing is left out rather than zeroed, so every
 * field here is optional and absence means "not attached to this reading",
 * never "zero".
 */

/** Estimated liquidation levels from Binance open-interest changes at Hyperliquid prices. An inference. */
export interface DerivedLiquidationMap {
  observed_at_ms: number
  /** Balance of estimated levels within 3% of price: positive means more sit above. */
  skew_3pct: number | null
  largest_above_pct: number | null
  largest_below_pct: number | null
}

/** Liquidations received from Bybit and Binance over the last hour. Other venues' recorded events. */
export interface DerivedCexLiquidations {
  observed_at_ms: number
  long_usd: number
  short_usd: number
  net_usd: number
  events: number
}

/** Resting bid against ask notional near price, from the aggregated Hyperliquid book. */
export interface DerivedRestingLiquidity {
  observed_at_ms: number
  imbalance: number | null
  bid_wall_bps: number | null
  ask_wall_bps: number | null
}

export interface DerivedContext {
  liquidation_map?: DerivedLiquidationMap
  cex_liquidations_1h?: DerivedCexLiquidations
  resting_liquidity?: DerivedRestingLiquidity
}

/** Mix into a snapshot type to read the context market-data attached to it. */
export interface WithDerived {
  derived?: DerivedContext
}
