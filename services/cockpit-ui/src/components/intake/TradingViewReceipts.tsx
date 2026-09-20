import type { TradingViewReceipt } from '../../api/tradingViewSetupTypes'
import { exactTime, receiptTitle, receiptVerdict } from './tradingViewText'
import styles from './TradingViewReceipts.module.css'

/** The newest TradingView alerts TradeSync stored, each with its verdict. Their content stays in the list below. */
export function TradingViewReceipts({ receipts, error }: { receipts: TradingViewReceipt[]; error: string | null }) {
  return (
    <div className={styles.wrap}>
      <span className="pipeline-detail-label">Latest TradingView alerts</span>
      {error && <p className={`${styles.empty} tone-bad`}>{error}</p>}
      {!error && receipts.length === 0 && (
        <p className={`${styles.empty} tone-dim`}>None stored yet. An alert appears here within 30 seconds of arriving.</p>
      )}
      {receipts.length > 0 && (
        <ul className={styles.list}>
          {receipts.map((receipt) => {
            const verdict = receiptVerdict(receipt)
            return (
              <li key={receipt.id} className={styles.item}>
                <span className={`pill ${receipt.accepted ? 'pill--good' : 'pill--bad'}`}>{receipt.accepted ? 'accepted' : 'refused'}</span>
                <span className={styles.what}>{receiptTitle(receipt)}</span>
                <time className={styles.when} dateTime={receipt.received_at}>{exactTime(receipt.received_at)}</time>
                <span className={`${styles.verdict} ${verdict.tone}`}>{verdict.text}</span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
