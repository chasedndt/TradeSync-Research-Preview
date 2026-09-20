import type { LiquidationData, MetricAvailability } from '../../../api/types'
import { proxyLine } from './liquidationSources'
import { SourceSection } from './SourceSection'
import styles from './Liquidations.module.css'

/**
 * The legacy proxy: a total estimated from a fall in open interest.
 *
 * This section deliberately renders a total and nothing else. The proxy splits
 * that total fifty-fifty between longs and shorts, and the previous panel drew
 * the two halves as a long figure beside a short figure — a direction the
 * source cannot support, presented exactly like the recorded events above it.
 * The split is not rendered at all, and the reason is stated in its place.
 */
export function ProxyEstimate({
  liquidations,
  metric,
}: {
  liquidations?: LiquidationData
  metric?: MetricAvailability
}) {
  const hour = liquidations?.horizons?.['1h']

  return (
    <SourceSection kind="legacy_proxy">
      {liquidations ? (
        <>
          <p className={styles.figure}>{proxyLine(hour?.total_usd)}</p>
          <ul className={styles.levels}>
            <li><span>Method</span> {liquidations.method}</li>
            <li><span>Standing in this reading</span> {metric?.status ?? 'not reported'}</li>
          </ul>
          {liquidations.source_note && <p className={styles.note}>{liquidations.source_note}</p>}
        </>
      ) : (
        <p className={styles.empty}>No proxy estimate in this reading.</p>
      )}
    </SourceSection>
  )
}
