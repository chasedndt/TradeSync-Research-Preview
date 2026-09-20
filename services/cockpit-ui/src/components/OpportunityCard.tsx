import { Link } from 'react-router-dom'
import type { OpportunityBriefCard } from '../api/opportunityBriefTypes'
import {
  conditionsCount,
  fitTone,
  fitWords,
  openedLine,
  priceWords,
  ratioWords,
  shortDigest,
  sideTone,
  stateTone,
  usdcWords,
} from './opportunity/brief/briefText'
import styles from './OpportunityCard.module.css'

/**
 * One opportunity in the list, from its stored brief: symbol and timeframe, side,
 * regime fit, how many entry conditions were met, the paper plan's stop, target,
 * risk and reward (or that none was ever set), the paper state, the evidence
 * digest and when it opened. Status and expiry are the API's; nothing is derived.
 */
export function OpportunityCard({ brief }: { brief: OpportunityBriefCard }) {
  const { plan } = brief
  const planned = plan.status !== 'none'

  return (
    <Link
      to={`/opportunities/${brief.id}`}
      className={`${styles.card} ${brief.status === 'expired' ? styles.expired : ''}`}
    >
      <div className={styles.head}>
        <span className={styles.symbol}>{brief.symbol}</span>
        <span className={styles.timeframe}>{brief.timeframe}</span>
        <span className={`${styles.side} tone-${sideTone(brief.side)}`}>{brief.side}</span>
        <span className={styles.status}>{brief.status}</span>
      </div>
      <dl className={styles.facts}>
        <div>
          <dt>Regime fit</dt>
          <dd className={`tone-${fitTone(brief.regime_fit.fit)}`}>{fitWords(brief.regime_fit.fit)}</dd>
        </div>
        <div><dt>Entry</dt><dd>{conditionsCount(brief.entry)}</dd></div>
        <div>
          <dt>Stop · target</dt>
          <dd>{planned ? `${priceWords(plan.stop)} · ${priceWords(plan.targets?.[0]?.level)}` : 'No paper plan set'}</dd>
        </div>
        <div>
          <dt>Risk · reward</dt>
          <dd>{planned ? `${usdcWords(plan.estimated_risk_usdc)} · ${usdcWords(plan.estimated_reward_usdc)}` : '—'}</dd>
        </div>
        <div><dt>Net reward to risk</dt><dd>{planned ? ratioWords(plan.net_reward_risk) : '—'}</dd></div>
        <div>
          <dt>Paper state</dt>
          <dd className={`tone-${stateTone(brief.state)}`}>{brief.state.label}</dd>
        </div>
      </dl>
      <p className={styles.meta}>{openedLine(brief.opened_at_s, brief.age_s)}</p>
      <p className={styles.meta}>Evidence digest {shortDigest(brief.provenance.evidence_digest)}</p>
    </Link>
  )
}
