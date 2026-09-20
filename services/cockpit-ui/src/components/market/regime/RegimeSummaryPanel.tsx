import { useRegimeSummary } from '../../../api/hooks/useRegimeSummary'
import { RegimeComponents } from './RegimeComponents'
import { RegimeConfidence } from './RegimeConfidence'
import { RegimeHistory } from './RegimeHistory'
import { headline, readingLine } from './regimeSummaryText'
import styles from './Regime.module.css'

/**
 * The regime for one market with the evidence behind it: the condition, the
 * confidence and what stands behind it, each required input with its source and
 * age, the readings that disagree, why confidence is not higher, and how the
 * recorded regime has changed.
 *
 * Every figure is calculated by the state API. The condition is never shown as
 * an unexplained "unknown": when it is not classified, the API names the inputs
 * that are missing and this panel renders them.
 */
export function RegimeSummaryPanel({ symbol }: { symbol: string }) {
  const query = useRegimeSummary(symbol)
  const data = query.data?.symbol === symbol ? query.data : undefined

  return (
    <section className="panel" aria-labelledby="regime-summary-title">
      <div className="panel-heading">
        <div>
          <h2 id="regime-summary-title">Regime summary</h2>
          <p>{headline(data)}</p>
        </div>
        <div className={styles.headActions}>
          {data && <span className={styles.reading}>{readingLine(data)}</span>}
          <button
            type="button"
            className="chip"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            {query.isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {query.isError && (
        <p className={styles.warn}>Regime summary unavailable: {(query.error as Error).message}</p>
      )}

      {data && (
        <div className={styles.body}>
          <RegimeConfidence summary={data} />
          <RegimeComponents summary={data} />
          <RegimeHistory summary={data} />
          <p className={styles.note}>{data.note}</p>
        </div>
      )}
    </section>
  )
}
