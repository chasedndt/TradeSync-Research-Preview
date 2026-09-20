import { AlertCircle } from 'lucide-react'
import { MetricStatusBadge } from './MetricStatusBadge'
import { RegimeBadge } from './RegimeBadge'
import { formatNumber } from './snapshotFormat'
import type { MarketSnapshot } from '../../../api/types'

// OI Panel
export function OIPanel({ snapshot }: { snapshot: MarketSnapshot }) {
  const oiMetric = snapshot.available_metrics.find((m) => m.metric === 'oi')
  const status = oiMetric?.status || 'UNAVAILABLE'

  if (status === 'UNAVAILABLE' || !snapshot.oi) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">OI data unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { oi } = snapshot

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <RegimeBadge regime={oi.regime} />
        <MetricStatusBadge status={status} />
      </div>

      <div className="text-center mb-2">
        <div className="text-2xl font-bold">${formatNumber(oi.current_usd)}</div>
        <div className="text-xs text-gray-500">Total Open Interest</div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        {['5m', '1h', '4h', '24h'].map((window) => {
          const data = oi.horizons[window]
          if (!data) return null
          return (
            <div key={window} className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500">{window}</div>
              <div className={`font-mono ${data.delta_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {data.delta_pct >= 0 ? '+' : ''}
                {data.delta_pct.toFixed(2)}%
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
