import type { CalendarEvent, OutlookKeyEvent } from '../api/types'
import { CaretDown, CaretUp } from './icons'
import { ReactionTable } from './thesis/KeyEvents'
import styles from './EventsStrip.module.css'

interface Props {
  event: CalendarEvent
  reaction?: OutlookKeyEvent
  open: boolean
  countdown: string
  onToggle: () => void
}

/**
 * One scheduled event on two lines: its rating, country and title, then when
 * it is and its measured reaction. A row with a reaction opens and closes when
 * clicked anywhere on it; the caret stays visible however narrow the panel, and
 * the open detail has its own hide control and keeps its table inside the panel.
 */
export function EventRow({ event: e, reaction: k, open, countdown, onToggle }: Props) {
  const lead = k?.reaction['BTC-PERP']?.['4h']
  const volatility = lead?.volatility_ratio == null ? 'Unmeasured volatility' : lead.volatility_ratio >= 1.5 ? 'High volatility expected' : lead.volatility_ratio >= 1.15 ? 'Elevated volatility expected' : 'Typical volatility expected'
  const summary = lead?.median_abs_move_pct != null
    ? `BTC ${lead.median_abs_move_pct.toFixed(2)}% over 4h · ${lead.volatility_ratio?.toFixed(1) ?? '—'}× usual`
    : 'measured reaction'
  const rowClass = [styles.event, e.market_moving ? styles.moving : '', k ? styles.expandable : '', open ? styles.eventOpen : ''].join(' ')

  return (
    <li className={[styles.item, e.minutes_until < 0 ? styles.past : ''].join(' ')}>
      <div
        className={rowClass}
        role={k ? 'button' : undefined}
        tabIndex={k ? 0 : undefined}
        aria-expanded={k ? open : undefined}
        title={k ? (open ? 'Hide the measured reaction' : 'Show how the market reacted to past releases') : undefined}
        onClick={k ? onToggle : undefined}
        onKeyDown={k ? (ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onToggle() }
          if (ev.key === 'Escape' && open) onToggle()
        } : undefined}
      >
        <span className={`${styles.impact} ${styles[`impact${e.impact}`]}`} title={`${e.impact} impact (feed rating)`}>
          {e.impact === 'Holiday' ? 'HOL' : e.impact[0]}
        </span>
        <span className={styles.country}>{e.country}</span>
        {e.url ? (
          <a className={styles.name} href={e.url} target="_blank" rel="noopener noreferrer" title={`${e.title} · open ${e.source}`}
            onClick={(ev) => ev.stopPropagation()}>
            {e.title} ↗
          </a>
        ) : (
          <span className={styles.name} title={e.title}>{e.title}</span>
        )}
        <span className={styles.toggle}>{k ? (open ? <CaretUp size={13} weight="bold" /> : <CaretDown size={13} weight="bold" />) : null}</span>
        <span className={styles.meta}>
          <span className={styles.when}>{countdown}</span>
          {(e.forecast || e.previous) && (
            <span className={styles.figures}>
              {e.forecast && <>forecast {e.forecast}</>}{e.forecast && e.previous && ' · '}{e.previous && <>previous {e.previous}</>}
            </span>
          )}
          {k && <span className={styles.reactionChip}>{volatility} · {summary}</span>}
        </span>
      </div>
      {open && k && (
        <div className={styles.detail}>
          <div className={styles.scenarioIntro}>
            <strong>Outcome scenario map</strong>
            <span>Compare the actual release with forecast; these are risk responses, not guaranteed price directions.</span>
          </div>
          <div className={styles.eventScenarios}>
            {eventScenarios(k.kind, e.title).map((scenario) => <div key={scenario.label}><strong>{scenario.label}</strong><p>{scenario.text}</p></div>)}
          </div>
          <div className={styles.tableScroll}><ReactionTable reaction={k.reaction} /></div>
          {k.guidance.map((g, i) => <p key={i} className={styles.guidance}>{g}</p>)}
          {k.articles.length > 0 && (
            <ul className={styles.articles}>
              {k.articles.slice(0, 4).map((a) => (
                <li key={a.url}><a href={a.url} target="_blank" rel="noopener noreferrer">{a.title || a.url}</a> <span>{a.domain}</span></li>
              ))}
            </ul>
          )}
          <button type="button" className={styles.hide} onClick={onToggle}>Hide reaction <CaretUp size={11} weight="bold" /></button>
        </div>
      )}
    </li>
  )
}

function eventScenarios(kind: string | null, title: string) {
  const text = `${kind ?? ''} ${title}`.toLowerCase()
  if (text.includes('rate') || text.includes('policy')) return [
    { label: 'Tighter / higher', text: 'A more restrictive result can pressure risk assets and lift volatility; wait for the first market structure response.' },
    { label: 'As expected', text: 'The decision may be priced in. Guidance, projections and the press conference can become the real surprise.' },
    { label: 'Easier / lower', text: 'An easier result can support risk appetite, but a growth scare can reverse that reaction. Confirm with price and liquidity.' },
  ]
  if (text.includes('cpi') || text.includes('inflation') || text.includes('pce')) return [
    { label: 'Hotter than forecast', text: 'A higher inflation surprise can reprice rates upward and increase risk-asset volatility.' },
    { label: 'Near forecast', text: 'A small surprise reduces the first-order impulse; the market may focus on components and revisions.' },
    { label: 'Cooler than forecast', text: 'A lower inflation surprise can ease rate pressure, unless it is read as evidence of weakening demand.' },
  ]
  if (text.includes('claim') || text.includes('employment') || text.includes('payroll')) return [
    { label: 'Stronger labour', text: 'A stronger result can support growth expectations while keeping policy tighter; direction is regime-dependent.' },
    { label: 'Near forecast', text: 'Limited surprise usually shifts attention to revisions, wages and the prevailing liquidity regime.' },
    { label: 'Weaker labour', text: 'A weaker result can support easing expectations or trigger growth concern. Let the measured reaction resolve the ambiguity.' },
  ]
  return [
    { label: 'Above forecast', text: 'Treat the size of the surprise as the catalyst; do not infer direction until price and liquidity confirm it.' },
    { label: 'Near forecast', text: 'A low-surprise result may leave the existing market regime in control.' },
    { label: 'Below forecast', text: 'The impulse can differ by regime. Use the measured reaction and market structure before acting.' },
  ]
}
