import type { BriefPlan as Plan, BriefPlanFixed, BriefPlanNone } from '../../../api/opportunityBriefTypes'
import { ageWords } from '../../market/readingTime'
import { atSeconds, isFixedPlan, priceWords, ratioWords, usdcWords } from './briefText'
import styles from './Brief.module.css'

const words = (value: string | null | undefined): string => (value ? value.split('_').join(' ') : '—')

/**
 * The paper plan: invalidation, stop, target, expiry, and the risk and reward it
 * was sized to, as frozen when a managed paper position opened. With no position
 * there are no levels, and the rules a plan would be set under are shown instead.
 */
export function BriefPlan({ plan }: { plan: Plan }) {
  return (
    <section className="panel" aria-labelledby="brief-plan-title">
      <div className="panel-heading">
        <div>
          <h3 id="brief-plan-title">Paper plan</h3>
          <p>{plan.detail}</p>
        </div>
      </div>
      {isFixedPlan(plan) ? <FixedPlan plan={plan} /> : <NoPlan plan={plan as BriefPlanNone} />}
    </section>
  )
}

function FixedPlan({ plan }: { plan: BriefPlanFixed }) {
  return (
    <>
      <dl className={styles.facts}>
        <div><dt>Invalidation</dt><dd>{priceWords(plan.invalidation.level)}</dd></div>
        <div><dt>Stop at entry</dt><dd>{priceWords(plan.stop)}</dd></div>
        <div><dt>Stop now</dt><dd>{priceWords(plan.invalidation.current_stop)} · {words(plan.invalidation.current_stop_rule)}</dd></div>
        {plan.targets.map((target, index) => (
          <div key={`${index}-${target.level}`}><dt>Target {plan.targets.length > 1 ? index + 1 : ''}</dt><dd>{priceWords(target.level)}</dd></div>
        ))}
        <div><dt>Entry price</dt><dd>{priceWords(plan.entry_price)}</dd></div>
        <div><dt>Estimated risk</dt><dd>{usdcWords(plan.estimated_risk_usdc)}</dd></div>
        <div><dt>Estimated reward</dt><dd>{usdcWords(plan.estimated_reward_usdc)}</dd></div>
        <div><dt>Declared cost budget</dt><dd>{usdcWords(plan.cost_budget_usdc)}</dd></div>
        <div><dt>Net reward to risk</dt><dd>{ratioWords(plan.net_reward_risk)}</dd></div>
        <div><dt>Time expiry</dt><dd>{atSeconds(plan.expiry_s)}</dd></div>
      </dl>
      <div className={styles.body}>
        <p className={styles.note}>
          {plan.invalidation.rule} Target: {plan.targets[0]?.basis ?? 'as stored'}. {plan.risk_basis}
        </p>
        <p className={styles.note}>
          Position {plan.status} · {plan.style ?? '—'} · rules {plan.rules_version ?? '—'} · opened {atSeconds(plan.opened_at_s)}
        </p>
        {plan.exit && (
          <p className={styles.text}>
            Closed by the {words(plan.exit.rule)} rule at {priceWords(plan.exit.price)} on {atSeconds(plan.exit.at_s)},
            net {usdcWords(plan.exit.net_estimate_usdc)}.
          </p>
        )}
      </div>
    </>
  )
}

function NoPlan({ plan }: { plan: BriefPlanNone }) {
  const rules = plan.rules_at_entry
  return (
    <div className={styles.body}>
      <p className={styles.text}>The rules a plan would be set under, by holding style ({rules.version}):</p>
      <div className="table-scroll">
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Style</th>
              <th scope="col">Stop</th>
              <th scope="col">Target</th>
              <th scope="col">Nearest target</th>
              <th scope="col">Longest hold</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(rules.styles).map(([style, rule]) => (
              <tr key={style}>
                <th scope="row">{style}</th>
                <td className={styles.mono}>{rule.stop_atr} × ATR on {rule.atr_interval}</td>
                <td className={styles.mono}>{rule.reward_risk} × the stop distance</td>
                <td className={styles.mono}>{rule.min_target_pct}% from entry</td>
                <td className={styles.mono}>{ageWords(rule.max_hold_s * 1000)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.note}>
        Every entry: planned risk at most {rules.max_planned_risk_usdc} USDC, net reward to risk at least{' '}
        {rules.min_net_reward_risk} to 1, and an opportunity no older than {ageWords(rules.max_opportunity_age_s * 1000)}.
      </p>
    </div>
  )
}
