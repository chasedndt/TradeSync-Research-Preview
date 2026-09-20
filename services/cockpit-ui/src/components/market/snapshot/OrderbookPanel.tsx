import { AlertCircle } from 'lucide-react'
import { MetricStatusBadge } from './MetricStatusBadge'
import { formatNumber } from './snapshotFormat'
import type { MarketSnapshot } from '../../../api/types'

// Orderbook Panel
export function OrderbookPanel({ snapshot }: { snapshot: MarketSnapshot }) {
  const obMetric = snapshot.available_metrics.find((m) => m.metric === 'orderbook')
  const status = obMetric?.status || 'UNAVAILABLE'

  if (status === 'UNAVAILABLE' || !snapshot.orderbook) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">Orderbook data unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { orderbook } = snapshot

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">SPREAD & DEPTH</span>
        <MetricStatusBadge status={status} />
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">Spread</div>
          <div className="font-mono">{orderbook.spread_bps.toFixed(2)} bps</div>
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">Mid Price</div>
          <div className="font-mono">${orderbook.mid_price.toLocaleString()}</div>
        </div>
      </div>

      <div className="space-y-1">
        <div className="text-xs text-gray-500">Depth (1%)</div>
        <div className="flex gap-1">
          <div className="flex-1 bg-green-900/30 rounded p-1.5 text-xs">
            <div className="text-green-400 font-mono">${formatNumber(orderbook.depth.bid_1pct_usd)}</div>
            <div className="text-[9px] text-gray-500">Bids</div>
          </div>
          <div className="flex-1 bg-red-900/30 rounded p-1.5 text-xs">
            <div className="text-red-400 font-mono">${formatNumber(orderbook.depth.ask_1pct_usd)}</div>
            <div className="text-[9px] text-gray-500">Asks</div>
          </div>
        </div>
        <div className="text-[10px] text-gray-600">
          Imbalance: {(orderbook.imbalance_1pct * 100).toFixed(1)}%
          {orderbook.imbalance_1pct > 0 ? ' (bid heavy)' : ' (ask heavy)'}
        </div>
      </div>
    </div>
  )
}
