import { Link } from 'react-router-dom'
import type { ContextOverviewResponse } from '../../api/types'
import { useHorizonPage } from '../../api/hooks/useHorizons'
import type { HorizonKey, HorizonPage, HorizonRead } from '../../api/horizonTypes'
import { formatPrice, formatWhen } from './format'
import styles from './Home.module.css'

const HORIZONS: HorizonKey[] = ['1h', '4h', '8h', '1d', '1w', '1m']

function readFor(page: HorizonPage | undefined, key: HorizonKey): HorizonRead | undefined {
  return page?.outlook.horizons.find((read) => read.key === key)
}

function tone(lean: HorizonRead['lean']) {
  return lean === 'up' ? 'tone-good' : lean === 'down' ? 'tone-bad' : 'tone-dim'
}

function HorizonCell({ read }: { read?: HorizonRead }) {
  if (!read?.available) return <span className={styles.horizonMissing}>—</span>
  const label = read.lean === 'up' ? 'UP' : read.lean === 'down' ? 'DOWN' : read.lean === 'mixed' ? 'MIXED' : 'NO EDGE'
  const mix = read.record?.same_state.outcome_mix
  return <span className={`${styles.horizonCell} ${tone(read.lean)}`} title={read.reason ?? `${read.label}: ${read.lean}`}>
    <strong>{label}</strong><small>{mix ? `↑${Math.round(mix.up * 100)} · ↔${Math.round(mix.range * 100)} · ↓${Math.round(mix.down * 100)}` : read.momentum?.change_pct == null ? 'record read' : `${read.momentum.change_pct >= 0 ? '+' : ''}${read.momentum.change_pct.toFixed(2)}%`}</small>
  </span>
}

function RangeLine({ page }: { page?: HorizonPage }) {
  const day = readFor(page, '1d')?.implied_range
  const week = readFor(page, '1w')?.implied_range
  return <span className={styles.rangeLine}>
    1d corridor {day ? `${formatPrice(day.low)}–${formatPrice(day.high)}` : 'measuring'} · 1w {week ? `${formatPrice(week.low)}–${formatPrice(week.high)}` : 'measuring'}
  </span>
}

/** Compact all-horizon briefing; edition history belongs on the Thesis page. */
export function MarketOverviewBoard({ context }: { context?: ContextOverviewResponse }) {
  const btc = useHorizonPage('BTC-PERP')
  const eth = useHorizonPage('ETH-PERP')
  const sol = useHorizonPage('SOL-PERP')
  const rows = [['BTC', btc.data], ['ETH', eth.data], ['SOL', sol.data]] as const
  const next = context?.providers.calendar?.data.next_market_moving
  const measured = [btc.data, eth.data, sol.data]
    .flatMap((page) => page ? Object.values(page.computed_at) : [])
    .filter((value): value is string => Boolean(value)).sort()
  const updated = measured[measured.length - 1]

  return <section className={`panel ${styles.overviewBoard}`} aria-labelledby="market-overview-title">
    <div className="panel-heading">
      <div><h2 id="market-overview-title">Market horizon map</h2><p>lower, intraday and higher-timeframe context · refreshes every minute</p></div>
      <div className={styles.overviewActions}><span className="metric-sub">{updated ? `measured ${new Date(updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'measuring…'}</span><Link className="panel-action" to="/timeframes">Open full timeframes →</Link></div>
    </div>
    {next && <div className={`${styles.eventAlert} ${next.minutes_until < 180 ? styles.eventAlertNear : ''}`}>
      <span className={styles.eventFlag}>MARKET-MOVING</span>
      <strong>{next.title}</strong>
      <span>{formatWhen(next.minutes_until)} · {next.country} · {next.impact} impact</span>
      {next.url && <a href={next.url} target="_blank" rel="noopener noreferrer">Source ↗</a>}
    </div>}
    <div className={styles.horizonTableWrap}>
      <table className={styles.horizonTable}>
        <thead><tr><th>Market</th>{HORIZONS.map((key) => <th key={key}>{key}</th>)}</tr></thead>
        <tbody>{rows.map(([symbol, page]) => <tr key={symbol}>
          <th><strong>{symbol}</strong><RangeLine page={page} /></th>
          {HORIZONS.map((key) => <td key={key}><HorizonCell read={readFor(page, key)} /></td>)}
        </tr>)}</tbody>
      </table>
    </div>
    <p className={styles.methodNote}>Arrows are historical up / range / down frequencies in matching states. Range uses an explicit volatility-relative band. These are not calibrated forecasts or guaranteed targets; open Timeframes to inspect every window and earned weight.</p>
  </section>
}
