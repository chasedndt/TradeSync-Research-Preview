import { SourceSection } from './SourceSection'
import styles from './Liquidations.module.css'

/**
 * How a position is forced out on the venue TradeSync actually trades, and what
 * that venue publishes about it.
 *
 * This section exists because its answer is "nothing": Hyperliquid publishes no
 * market-wide liquidation feed, so there is no Hyperliquid liquidation reading
 * anywhere on this page. Every figure above and below comes from somewhere
 * else, and without saying so plainly a reader would take them for Hyperliquid's.
 */
export function VenueMechanics() {
  return (
    <SourceSection kind="venue_mechanics">
      <ul className={styles.levels}>
        <li>
          <span>Forced close</span> a position is closed when its margin falls to the venue&apos;s maintenance
          requirement; the venue, not TradeSync, decides and executes it.
        </li>
        <li>
          <span>Published feed</span> none. Hyperliquid does not publish a market-wide stream of liquidations, so
          none can be counted here.
        </li>
        <li>
          <span>Own positions</span> TradeSync holds no live position to be liquidated: paper entries stay paused
          and execution is closed.
        </li>
      </ul>
      <p className={styles.note}>
        The feature catalog keeps a place for a side-labelled Hyperliquid liquidation feed and marks it unavailable,
        so nothing substitutes for it.
      </p>
    </SourceSection>
  )
}
