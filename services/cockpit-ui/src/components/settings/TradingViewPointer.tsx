import { Link } from 'react-router-dom'
import { Webhook } from 'lucide-react'
import { useTradingViewSetup } from '../../api/hooks/useTradingViewSetup'
import { ReadingStamp } from '../ReadingStamp'
import { lastReceiptLine, secretLine } from '../intake/tradingViewText'
import styles from './TradingViewPointer.module.css'

/** A short pointer from Settings to the TradingView setup on Knowledge intake, with the secret shown only as configured or not. */
export function TradingViewPointer() {
  const setup = useTradingViewSetup()
  return (
    <section className="card" aria-label="TradingView alerts">
      <h3 className="text-sm font-medium text-gray-400 mb-4 flex items-center gap-2">
        <Webhook size={14} />
        TradingView alerts
      </h3>
      <p className={styles.text}>
        {setup.data
          ? secretLine(setup.data.secret_configured)
          : setup.isError
            ? `TradingView setup unavailable: ${setup.error?.message ?? 'no answer'}`
            : 'Checking the webhook secret…'}
      </p>
      {setup.data && <p className={styles.text}>{lastReceiptLine(setup.data.receipts)}</p>}
      <ReadingStamp at={setup.dataUpdatedAt || null} onRefresh={() => void setup.refetch()} refreshing={setup.isFetching} />
      <p className={styles.text}>
        The webhook address, the message to paste into TradingView, the steps and the latest alerts are on{' '}
        <Link to="/intake">Knowledge intake</Link>.
      </p>
    </section>
  )
}
