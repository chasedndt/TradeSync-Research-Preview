import { AlertCircle } from 'lucide-react'
import { MetricStatusBadge } from './MetricStatusBadge'
import { RegimeBadge } from './RegimeBadge'
import { formatPct } from './snapshotFormat'
import type { MarketSnapshot } from '../../../api/types'

// Funding Panel
export function FundingPanel({ snapshot }: { snapshot: MarketSnapshot }) {
  const fundingMetric = snapshot.available_metrics.find((m) => m.metric === 'funding')
  const status = fundingMetric?.status || 'UNAVAILABLE'

  if (status === 'UNAVAILABLE' || !snapshot.funding) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">Funding data unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { funding } = snapshot

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <RegimeBadge regime={funding.regime} />
        <MetricStatusBadge status={status} note={fundingMetric?.note} />
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">Current</div>
          <div className="font-mono">{formatPct(funding.horizons.now, 4)}</div>
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">8h Avg</div>
          <div className="font-mono">{formatPct(funding.horizons.h8, 4)}</div>
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">24h Avg</div>
          <div className="font-mono">{formatPct(funding.horizons.h24, 4)}</div>
        </div>
        <div className="bg-gray-900/50 rounded p-2">
          <div className="text-gray-500">Annualized</div>
          <div className={`font-mono ${funding.annualized_24h > 0 ? 'text-green-400' : 'text-red-400'}`}>
            {formatPct(funding.annualized_24h)}
          </div>
        </div>
      </div>
    </div>
  )
}
