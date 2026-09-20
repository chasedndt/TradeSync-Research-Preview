import type { DerivedCexLiquidations } from '../../../api/liquidationSourceTypes'
import { LiquidationsReceived } from '../LiquidationsReceived'
import { readAt } from '../readingTime'
import { receivedLine } from './liquidationSources'
import { SourceSection } from './SourceSection'
import styles from './Liquidations.module.css'

/**
 * Liquidations Bybit and Binance actually published, each with the side that
 * was closed. Sides are shown here because the venues published them.
 *
 * The windowed chart is the existing panel, which already reads these events
 * from the recorded history; what is added around it is the hour summary
 * market-data attached to this reading, and the standing that says what the
 * source is.
 */
export function ObservedLiquidations({ symbol, hour }: { symbol: string; hour?: DerivedCexLiquidations }) {
  return (
    <SourceSection kind="observed_events">
      <p className={styles.basis}>{receivedLine(hour)}</p>
      {hour && <p className={styles.note}>Hour summary read {readAt(hour.observed_at_ms)}.</p>}
      <LiquidationsReceived symbol={symbol} />
    </SourceSection>
  )
}
