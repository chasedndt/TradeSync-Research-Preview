import { AlertCircle } from 'lucide-react'
import { MetricStatusBadge } from './MetricStatusBadge'
import { RegimeBadge } from './RegimeBadge'
import { formatNumber } from './snapshotFormat'
import type { MarketSnapshot } from '../../../api/types'

// Volume Panel
export function VolumePanel({ snapshot }: { snapshot: MarketSnapshot }) {
  const volMetric = snapshot.available_metrics.find((m) => m.metric === 'volume')
  const status = volMetric?.status || 'UNAVAILABLE'

  if (status === 'UNAVAILABLE' || !snapshot.volume) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">Volume data unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { volume } = snapshot

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <RegimeBadge regime={volume.regime} />
        <MetricStatusBadge status={status} />
      </div>

      <div className="text-center mb-2">
        <div className="text-2xl font-bold">${formatNumber(volume.horizons['24h'] || 0)}</div>
        <div className="text-xs text-gray-500">24h Volume</div>
      </div>

      {volume.cvd && (
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-xs text-gray-500 mb-1">CVD (24h)</div>
          <div className={`font-mono text-sm ${(volume.cvd['24h'] || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {(volume.cvd['24h'] || 0) >= 0 ? '+' : ''}${formatNumber(volume.cvd['24h'] || 0)}
          </div>
          {volume.cvd_method === 'candle_proxy' && (
            <div className="text-[9px] text-yellow-600">PROXY: estimated from candles</div>
          )}
        </div>
      )}
    </div>
  )
}
