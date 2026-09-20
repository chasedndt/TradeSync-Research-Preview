import type { DerivedLiquidationMap } from '../../../api/liquidationSourceTypes'
import { readAt } from '../readingTime'
import { skewWords } from './liquidationSources'
import { SourceSection } from './SourceSection'
import styles from './Liquidations.module.css'

const pct = (value: number | null | undefined): string =>
  value == null || !Number.isFinite(value) ? 'none within range' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`

/**
 * Where leveraged positions would be forced out, inferred from open-interest
 * changes priced at Hyperliquid.
 *
 * Nobody was liquidated here. What this can say is where the estimated levels
 * sit relative to price, which is a statement about placement — deliberately
 * not a long or short read, and never counted as an event.
 */
export function InferredPressure({ map }: { map?: DerivedLiquidationMap }) {
  return (
    <SourceSection kind="inferred_pressure">
      {map ? (
        <>
          <p className={styles.basis}>{skewWords(map.skew_3pct)}</p>
          <ul className={styles.levels}>
            <li><span>Largest cluster above price</span> {pct(map.largest_above_pct)}</li>
            <li><span>Largest cluster below price</span> {pct(map.largest_below_pct)}</li>
          </ul>
          <p className={styles.note}>Inferred {readAt(map.observed_at_ms)}.</p>
        </>
      ) : (
        <p className={styles.empty}>
          No estimate attached to this reading. The estimate is refreshed every few minutes and is left out rather
          than carried forward once it ages.
        </p>
      )}
    </SourceSection>
  )
}
