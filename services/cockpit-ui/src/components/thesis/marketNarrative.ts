import type { HorizonKey, HorizonPage, HorizonRead } from '../../api/horizonTypes'
import type { MarketOutlook } from '../../api/types'

export function horizon(page: HorizonPage | undefined, key: HorizonKey): HorizonRead | undefined {
  return page?.outlook.horizons.find((item) => item.key === key)
}

export function price(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return 'an unconfirmed level'
  return value >= 1000
    ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    : `$${value.toLocaleString(undefined, { maximumFractionDigits: 3 })}`
}

function trendPhrase(read: HorizonRead | undefined, subject: string) {
  if (!read?.available || !read.trend) return `${subject} does not yet have enough retained history for a reliable description`
  const phrases: Record<string, string> = {
    above_rising: `${subject} is above an average that is still climbing`,
    above_falling: `${subject} has recovered above its average, although that average is still falling`,
    below_rising: `${subject} has slipped below an average that is still climbing`,
    below_falling: `${subject} is below a falling average`,
  }
  return phrases[read.trend.state] ?? `${subject} has a mixed technical picture`
}

function momentumPhrase(read: HorizonRead | undefined) {
  if (!read?.available || !read.momentum) return 'Momentum is not yet measured'
  return read.momentum.state === 'up' ? 'Buyers have recently regained ground' : 'Sellers still control the latest move'
}

function agreement(day: HorizonRead | undefined, fourHour: HorizonRead | undefined) {
  const d = day?.lean
  const f = fourHour?.lean
  if (d === 'up' && f === 'up') return 'The daily and four-hour charts are improving together, so pullbacks can be watched for support rather than chased at the top of a candle.'
  if (d === 'down' && f === 'down') return 'The daily and four-hour charts are weakening together, so rallies should be treated cautiously until price proves it can reclaim resistance.'
  return 'The daily and four-hour charts do not yet agree. That usually favours patience at the edges of the range instead of a trade through the middle.'
}

function relativeSentence(btc: HorizonRead | undefined, eth: HorizonRead | undefined) {
  const b = btc?.momentum?.change_pct
  const e = eth?.momentum?.change_pct
  if (b == null || e == null) return 'Ethereum relative strength is not available in the current evidence.'
  if (Math.abs(e - b) < 0.25) return 'Ethereum and Bitcoin are moving at a similar pace, so there is no clear rotation signal between them.'
  return e > b
    ? 'Ethereum is recovering faster than Bitcoin today. That is an early sign of improving risk appetite, but it is not enough on its own to call a broad altcoin run.'
    : 'Bitcoin is holding up better than Ethereum today. That keeps the market defensive and makes broad altcoin exposure less convincing.'
}

export interface MarketNarrative {
  headline: string
  overview: string
  week: string
  session: string
  ethereum: string
  catalyst: string
  bullCase: string
  waitCase: string
  bearCase: string
}

/** Turns measured chart state into an editorial explanation without inventing unavailable evidence. */
export function buildMarketNarrative(btc: HorizonPage | undefined, eth: HorizonPage | undefined, outlook: MarketOutlook): MarketNarrative {
  const month = horizon(btc, '1m')
  const week = horizon(btc, '1w')
  const day = horizon(btc, '1d')
  const fourHour = horizon(btc, '4h')
  const ethDay = horizon(eth, '1d')
  const lead = outlook.leads.find((item) => item.symbol === 'BTC-PERP')
  const support = day?.levels?.recent_low ?? lead?.low_24h
  const resistance = day?.levels?.recent_high ?? lead?.high_24h
  const pivot = day?.levels?.trend_flips_at
  const nextEvent = outlook.key_events[0]
  const monthlyStrong = month?.trend?.state === 'above_rising' || month?.trend?.state === 'above_falling'
  const weeklyStrong = week?.trend?.state === 'above_rising' || week?.trend?.state === 'above_falling'

  const headline = monthlyStrong && weeklyStrong
    ? 'Bitcoin is constructive, but the next breakout still needs confirmation'
    : monthlyStrong
      ? 'Bitcoin’s larger trend is intact, while the weekly chart is still repairing'
      : 'Bitcoin remains under pressure until it can reclaim the weekly structure'

  return {
    headline,
    overview: `Bitcoin is trading near ${price(btc?.outlook.last_close ?? lead?.last)}. On the monthly chart, ${trendPhrase(month, 'Bitcoin').replace(/^Bitcoin /, 'price ')}, while on the weekly chart, ${trendPhrase(week, 'price')}. In plain English, the larger trend and the current week are ${monthlyStrong === weeklyStrong ? 'telling a broadly consistent story' : 'not yet telling the same story'}, so this is not a market to reduce to a one-word bullish or bearish label.`,
    week: `For this week, the important area is between support near ${price(support)} and resistance near ${price(resistance)}. ${momentumPhrase(week)}. Holding above ${price(pivot ?? support)} keeps the recovery credible; a sustained break above ${price(resistance)} would show that buyers have accepted higher prices, while a return below ${price(support)} would damage the recovery.`,
    session: `${agreement(day, fourHour)} The current 24-hour trading area is ${price(lead?.low_24h)} to ${price(lead?.high_24h)}. Until price leaves that area with follow-through, movement inside it is context rather than a fresh trade signal.`,
    ethereum: relativeSentence(day, ethDay),
    catalyst: nextEvent
      ? `${nextEvent.title} is the next scheduled market event. The forecast is ${nextEvent.forecast || 'not supplied'} versus ${nextEvent.previous || 'no recorded previous value'}. Because the result is not known in advance, the sensible plan is to watch whether Bitcoin holds support or clears resistance after the release rather than guess the number.`
      : 'No scheduled high-impact event is attached to this edition. Unscheduled headlines can still move the market, so the chart levels remain the decision boundary.',
    bullCase: `A stronger case begins only if Bitcoin holds ${price(pivot ?? support)} and then closes through ${price(resistance)} with the daily and four-hour charts improving together.`,
    waitCase: `If price stays between ${price(support)} and ${price(resistance)}, the market is still deciding. The middle of that range offers poor reward for taking directional risk.`,
    bearCase: `A sustained move below ${price(support)} would invalidate the recovery idea. A short case still needs follow-through below that level; the first break alone is not enough.`,
  }
}
