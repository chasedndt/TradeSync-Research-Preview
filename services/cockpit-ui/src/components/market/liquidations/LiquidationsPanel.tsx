import type { WithDerived } from '../../../api/liquidationSourceTypes'
import type { MarketSnapshot } from '../../../api/types'
import { readAt } from '../readingTime'
import { InferredPressure } from './InferredPressure'
import { ObservedLiquidations } from './ObservedLiquidations'
import { ProxyEstimate } from './ProxyEstimate'
import { VenueMechanics } from './VenueMechanics'
import styles from './Liquidations.module.css'

/**
 * Liquidations, with the four different things that were previously shown as
 * one figure told apart: liquidations another venue actually published, how
 * forced closes work on Hyperliquid and what it does not publish, levels
 * inferred from open interest, and the legacy proxy estimate.
 *
 * They are ordered strongest evidence first, and each states what it is and
 * whether a side may be attached to it before any figure appears.
 */
export function LiquidationsPanel({
  symbol,
  snapshot,
  onRefresh,
  refreshing,
}: {
  symbol: string
  snapshot?: MarketSnapshot & WithDerived
  onRefresh: () => void
  refreshing: boolean
}) {
  const derived = snapshot?.derived
  const metric = snapshot?.available_metrics?.find((item) => item.metric === 'liquidations')

  return (
    <section className="panel" aria-labelledby="liquidations-title">
      <div className="panel-heading">
        <div>
          <h2 id="liquidations-title">Liquidations</h2>
          <p>Four separate sources, strongest evidence first · Hyperliquid publishes none of its own</p>
        </div>
        <div className={styles.headActions}>
          {snapshot && <span className={styles.reading}>Market read {readAt(snapshot.ts)}</span>}
          <button type="button" className="chip" onClick={onRefresh} disabled={refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>
      <div className={styles.body}>
        <ObservedLiquidations symbol={symbol} hour={derived?.cex_liquidations_1h} />
        <VenueMechanics />
        <InferredPressure map={derived?.liquidation_map} />
        <ProxyEstimate liquidations={snapshot?.liquidations} metric={metric} />
      </div>
    </section>
  )
}
