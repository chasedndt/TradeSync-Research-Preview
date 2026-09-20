/**
 * What each liquidation reading actually is, and whether it may be shown with a side.
 *
 * Four different things were rendered as one "Liquidations" card, and the
 * weakest of them was the one that looked most like fact: the legacy proxy
 * estimates a total from a fall in open interest and then splits it fifty-fifty
 * between longs and shorts. The Cockpit drew that split as a long figure beside
 * a short figure, which is a direction the source cannot support. The feature
 * catalog says so in as many words — "the current 50/50 long-short split is not
 * observed market truth", and the reserved direct-flow feature is marked "never
 * substitute the OI proxy as observed direction".
 *
 * So each source is classified once, here, and whether a side may be shown is a
 * property of the source rather than a decision each panel makes for itself.
 *
 * The four, weakest last:
 *
 * `observed_events`
 *     Liquidations Bybit and Binance actually published, each with the side of
 *     the position that was closed. Real events with a real side — but another
 *     venue's, never Hyperliquid's.
 * `venue_mechanics`
 *     How liquidation works on the venue TradeSync trades, and what it does not
 *     publish. Hyperliquid has no market-wide liquidation feed, so there is no
 *     Hyperliquid liquidation reading to show at all.
 * `inferred_pressure`
 *     Where leveraged positions would be forced out, inferred from
 *     open-interest changes priced at Hyperliquid. It can say which side holds
 *     more estimated levels; it cannot say anyone was liquidated.
 * `legacy_proxy`
 *     A total estimated from a fall in open interest, with an assumed split.
 *     No side, ever.
 */

export type SourceKind = 'observed_events' | 'venue_mechanics' | 'inferred_pressure' | 'legacy_proxy'

export interface SourceStanding {
  kind: SourceKind
  title: string
  /** Whether a long/short side may be attached to anything from this source. */
  directionSupported: boolean
  /** What the reading is. */
  basis: string
  /** Why a side is or is not shown. */
  directionNote: string
  /** The standing the API gives this source. */
  authority: string
}

export const SOURCE_STANDING: Record<SourceKind, SourceStanding> = {
  observed_events: {
    kind: 'observed_events',
    title: 'Liquidations received',
    directionSupported: true,
    basis:
      'Individual liquidations Bybit and Binance published, each carrying the side of the position that was closed. '
      + 'Bybit reports a bankruptcy price and Binance an average fill price.',
    directionNote:
      'Sides are shown: each event names the side that was closed, as the venue published it.',
    authority: 'context_only',
  },
  venue_mechanics: {
    kind: 'venue_mechanics',
    title: 'Hyperliquid mechanics',
    directionSupported: false,
    basis:
      'How a position is forced out on the venue TradeSync trades, and what that venue publishes about it.',
    directionNote:
      'No side is shown: Hyperliquid publishes no market-wide liquidation feed, so there is no Hyperliquid '
      + 'liquidation event to attach a side to.',
    authority: 'authoritative_market',
  },
  inferred_pressure: {
    kind: 'inferred_pressure',
    title: 'Inferred pressure',
    directionSupported: false,
    basis:
      'Where leveraged positions would be forced out, inferred from Binance open-interest changes priced at '
      + 'Hyperliquid with an assumed leverage mix, and cleared once price trades through them.',
    directionNote:
      'No side is claimed: this says which side holds more estimated levels, which is where price might be drawn, '
      + 'not that anyone was liquidated.',
    authority: 'context_only',
  },
  legacy_proxy: {
    kind: 'legacy_proxy',
    title: 'Legacy proxy estimate',
    directionSupported: false,
    basis:
      'A total estimated from a fall in open interest. It is a diagnostic kept for continuity, not a reading of '
      + 'any liquidation that happened.',
    directionNote:
      'No side is shown: the proxy splits its total fifty-fifty between longs and shorts, and that split is an '
      + 'assumption rather than anything measured. Showing it as a long figure beside a short figure would read '
      + 'as a fact the source cannot support.',
    authority: 'proxy_only',
  },
}

/** Whether anything from this source may carry a long or short side. */
export const directionAllowed = (kind: SourceKind): boolean => SOURCE_STANDING[kind].directionSupported

/** The side of a recorded event, in words. Refused outright for a source that cannot support one. */
export function sideWords(kind: SourceKind, side: string | null | undefined): string {
  if (!directionAllowed(kind)) {
    throw new Error(`${kind} cannot carry a side; render ${SOURCE_STANDING[kind].directionNote} instead`)
  }
  if (side === 'long') return 'longs closed'
  if (side === 'short') return 'shorts closed'
  return 'side not given'
}

/** A compact dollar figure: $1.2m, $840k, $95. */
export function usd(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  const sign = value < 0 ? '−' : ''
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}b`
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}m`
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}k`
  return `${sign}$${abs.toFixed(0)}`
}

/**
 * What the recorded hour shows, with its sides — this source supports them.
 * "Net" is longs minus shorts over the window, a description of what was recorded.
 */
export function receivedLine(totals: { long_usd: number; short_usd: number; net_usd: number; events: number } | undefined): string {
  if (!totals) return 'No liquidations recorded from Bybit or Binance in the last hour.'
  if (totals.events === 0) return 'No liquidation was recorded from Bybit or Binance in the last hour.'
  const heavier = totals.net_usd > 0 ? 'longs' : totals.net_usd < 0 ? 'shorts' : 'neither side'
  const events = totals.events === 1 ? '1 event' : `${totals.events} events`
  return `${events}: ${usd(totals.long_usd)} of longs and ${usd(totals.short_usd)} of shorts closed, `
    + `${heavier === 'neither side' ? 'evenly split' : `${heavier} the heavier side`}.`
}

/**
 * Where the estimated levels sit relative to price.
 *
 * This is deliberately a statement about placement, not direction: "more
 * estimated levels sit above price" says where the map put them, and says
 * nothing about which way price will go or that anyone was liquidated.
 */
export function skewWords(skew: number | null | undefined): string {
  if (skew == null || !Number.isFinite(skew)) return 'No estimated levels within 3% of price.'
  if (skew > 0) return `More estimated levels sit above price than below it, within 3% (balance ${skew.toFixed(2)}).`
  if (skew < 0) return `More estimated levels sit below price than above it, within 3% (balance ${skew.toFixed(2)}).`
  return 'Estimated levels are evenly placed above and below price, within 3%.'
}

/** The proxy's total, with no side and the reason there is none. */
export function proxyLine(totalUsd: number | null | undefined): string {
  return totalUsd == null || !Number.isFinite(totalUsd)
    ? 'No proxy estimate in this reading.'
    : `${usd(totalUsd)} estimated over the last hour, as a total only.`
}
