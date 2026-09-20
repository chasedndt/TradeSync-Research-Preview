import { useHorizonPage } from '../../api/hooks/useHorizons'
import type { HorizonKey, HorizonRead } from '../../api/horizonTypes'
import styles from './InteractiveThesisPlayer.module.css'

const HORIZON_FOR_INTERVAL: Record<string, HorizonKey> = { '1h': '1h', '2h': '4h', '4h': '4h', '8h': '8h', '12h': '1d', '1d': '1d', '1w': '1w' }

function stateWords(read: HorizonRead) {
  const trend = read.trend?.state.replace('_', ' ') ?? 'unavailable'
  const momentum = read.momentum?.state ?? 'unavailable'
  if (trend.startsWith('above rising') && momentum === 'up') return 'trend and momentum aligned higher'
  if (trend.startsWith('below falling') && momentum === 'down') return 'trend and momentum aligned lower'
  return `${trend}; ${momentum} momentum — transition or pullback conditions`
}

export function HorizonLens({ symbol, interval }: { symbol: string; interval: string }) {
  const page = useHorizonPage(symbol)
  const horizon = HORIZON_FOR_INTERVAL[interval] ?? '1d'
  const read = page.data?.outlook.horizons.find((item) => item.key === horizon)
  const record = read?.record?.same_state
  const mix = record?.outcome_mix
  if (page.isLoading) return <div className={styles.lens}><span>Measuring horizon record…</span></div>
  if (!read?.available || !record) return <div className={styles.lens}><strong>{horizon} context unavailable</strong><span>{read?.reason ?? 'No measured record.'}</span></div>
  return <div className={styles.lens}>
    <div className={styles.lensHead}><strong>{read.label} evidence lens</strong><span>{record.independent_windows} non-overlapping windows</span></div>
    <p>{stateWords(read)}. Current move {read.momentum?.change_pct == null ? '—' : `${read.momentum.change_pct >= 0 ? '+' : ''}${read.momentum.change_pct.toFixed(2)}%`}.</p>
    {mix ? <>
      <div className={styles.probabilities} aria-label={`Historical outcomes: up ${Math.round(mix.up * 100)}%, range ${Math.round(mix.range * 100)}%, down ${Math.round(mix.down * 100)}%`}>
        <span className={styles.probUp} style={{ width: `${mix.up * 100}%` }} />
        <span className={styles.probRange} style={{ width: `${mix.range * 100}%` }} />
        <span className={styles.probDown} style={{ width: `${mix.down * 100}%` }} />
      </div>
      <div className={styles.probLabels}><b>UP {Math.round(mix.up * 100)}%</b><b>RANGE {Math.round(mix.range * 100)}%</b><b>DOWN {Math.round(mix.down * 100)}%</b></div>
      <small>Historical outcomes in matching states, not a calibrated forecast. “Range” means within ±{mix.range_band_pct.toFixed(2)}% over this horizon.</small>
    </> : <small>Three-state history will appear after the refreshed measurement uses the current schema.</small>}
  </div>
}
