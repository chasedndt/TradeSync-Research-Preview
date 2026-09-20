import { useRegimeFit, useThesisAdherence } from '../../../api/hooks/useReconciliation'
import { abstentionText, departureText, ratioText, utcStamp } from './reconciliationFormat'
import styles from './OutcomeMetrics.module.css'

const FIT_WINDOW_HOURS = 168
const DEPARTURES_LISTED = 10

/** Thesis adherence and regime fit, both measured from evidence frozen at entry and never from a fresh market read. */
export function OutcomeMetrics() {
  const adherence = useThesisAdherence()
  const fit = useRegimeFit(FIT_WINDOW_HOURS)
  const a = adherence.data
  const f = fit.data
  const departed = a ? a.positions.filter((position) => position.departures.length > 0).slice(0, DEPARTURES_LISTED) : []

  return (
    <div className={styles.metrics}>
      <h4>Outcome measures from frozen evidence</h4>
      <div className={styles.pair}>
        <article className={styles.measure} aria-labelledby="thesis-adherence-title">
          <h5 id="thesis-adherence-title">Thesis adherence</h5>
          <p className={styles.explain}>
            Whether each paper position followed the plan it was opened under: entry inside its zone, stop and target respected, held no longer than planned, exit by a declared rule. Not whether it made money.
          </p>
          {adherence.isLoading && <p>Reading…</p>}
          {adherence.isError && <p role="alert" className="tone-warn">Unavailable: {adherence.error.message}</p>}
          {a && (
            <>
              <p className={styles.figure}>{ratioText(a.summary.mean_adherence)}</p>
              <p>
                {a.summary.positions_scored} of {a.summary.positions} positions scored · {a.summary.checks_failed} departure{a.summary.checks_failed === 1 ? '' : 's'} · {a.summary.checks_abstained} check{a.summary.checks_abstained === 1 ? '' : 's'} abstained
              </p>
              {a.summary.positions === 0 && <p className={styles.explain}>No managed paper position yet, so there is nothing to score. That is not a score of zero.</p>}
              {departed.length > 0 && (
                <ul className={styles.list}>
                  {departed.map((position) => (
                    <li key={position.position_id}>
                      {position.symbol} opened {utcStamp(position.opened_at)}: {departureText(position.departures)}
                    </li>
                  ))}
                </ul>
              )}
              <p className={styles.time}>Reading {utcStamp(a.generated_at)}</p>
            </>
          )}
        </article>

        <article className={styles.measure} aria-labelledby="regime-fit-title">
          <h5 id="regime-fit-title">Regime fit</h5>
          <p className={styles.explain}>
            Whether each call fired into the regime its own rulebook expected, judged against the rulebook frozen on that call so a later rulebook cannot rewrite the verdict.
          </p>
          {fit.isLoading && <p>Reading…</p>}
          {fit.isError && <p role="alert" className="tone-warn">Unavailable: {fit.error.message}</p>}
          {f && (
            <>
              <p className={styles.figure}>{ratioText(f.summary.regime_fit_rate)}</p>
              <p>
                {f.summary.judged} of {f.summary.calls} calls judged · {f.summary.fit} fit, {f.summary.misfit} misfit · {abstentionText(f.summary.abstained_by_reason)}
              </p>
              <p className={styles.time}>
                Reading {utcStamp(f.generated_at)} · window {utcStamp(f.window.from)} to {utcStamp(f.window.to)}
              </p>
            </>
          )}
        </article>
      </div>
    </div>
  )
}
