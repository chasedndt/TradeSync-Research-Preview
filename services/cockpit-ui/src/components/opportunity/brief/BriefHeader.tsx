import type { OpportunityBrief } from '../../../api/opportunityBriefTypes'
import {
  atSeconds,
  conditionsCount,
  fitTone,
  fitWords,
  openedLine,
  readLine,
  sideTone,
  stateTone,
} from './briefText'
import styles from './Brief.module.css'

/**
 * Symbol and timeframe, side, status, regime fit, how many entry conditions were
 * met, the paper state, and when the opportunity opened and was read. Every value
 * is the brief's own; the two stored scores are shown as they were stored.
 */
export function BriefHeader({
  brief,
  onRefresh,
  refreshing,
}: {
  brief: OpportunityBrief
  onRefresh: () => void
  refreshing: boolean
}) {
  const scores = brief.stored_scores
  const expires = brief.expires_at_s == null ? '' : ` · expires ${atSeconds(brief.expires_at_s)}`

  return (
    <section className="panel" aria-labelledby="brief-title">
      <div className="panel-heading">
        <div>
          <h2 id="brief-title">{brief.symbol} · {brief.timeframe}</h2>
          <p>{openedLine(brief.opened_at_s, brief.age_s)}{expires}</p>
        </div>
        <div className={styles.headActions}>
          <span className={styles.reading}>{readLine(brief.read_at_s)}</span>
          <button type="button" className="chip" onClick={onRefresh} disabled={refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>
      <dl className={styles.facts}>
        <div><dt>Side</dt><dd className={`tone-${sideTone(brief.side)}`}>{brief.side}</dd></div>
        <div><dt>Status</dt><dd>{brief.status}</dd></div>
        <div><dt>Regime fit</dt><dd className={`tone-${fitTone(brief.regime_fit.fit)}`}>{fitWords(brief.regime_fit.fit)}</dd></div>
        <div><dt>Entry</dt><dd>{conditionsCount(brief.entry)}</dd></div>
        <div><dt>Paper state</dt><dd className={`tone-${stateTone(brief.state)}`}>{brief.state.label}</dd></div>
        <div><dt>Directional score, as stored</dt><dd>{scores.directional_score == null ? '—' : scores.directional_score.toFixed(3)}</dd></div>
        <div><dt>Evidence coverage, as stored</dt><dd>{scores.evidence_coverage_pct == null ? '—' : `${scores.evidence_coverage_pct.toFixed(0)}%`}</dd></div>
      </dl>
      <div className={styles.body}>
        <p className={styles.text}>{brief.state.detail}</p>
        <p className={styles.note}>
          {brief.state.execution_enabled
            ? 'EXECUTION_ENABLED is true in this deployment.'
            : 'Paper only: EXECUTION_ENABLED is false, so no order reaches the venue.'}{' '}
          {scores.basis}
        </p>
      </div>
    </section>
  )
}
