import { AlertCircle } from 'lucide-react'
import { MetricStatusBadge } from './MetricStatusBadge'
import { formatNumber } from './snapshotFormat'
import type { MarketSnapshotWithMicrostructure } from '../../../api/types'

// Phase 3C: Liquidity Panel
export function LiquidityPanel({ snapshot }: { snapshot: MarketSnapshotWithMicrostructure }) {
  const obMetric = snapshot.available_metrics.find((m) => m.metric === 'orderbook')
  const status = obMetric?.status || 'UNAVAILABLE'
  const microstructure = snapshot.microstructure

  if (status === 'UNAVAILABLE' || !microstructure) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800 border-dashed flex flex-col items-center justify-center text-center">
        <AlertCircle size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-600">Microstructure data unavailable</p>
        <MetricStatusBadge status="UNAVAILABLE" />
      </div>
    )
  }

  const { spread_bps, depth_usd, impact_est_bps, liquidity_score, book_heatmap } = microstructure

  // Determine liquidity health color
  const liquidityColor = liquidity_score >= 0.7
    ? 'text-green-400'
    : liquidity_score >= 0.4
      ? 'text-yellow-400'
      : 'text-red-400'

  const liquidityBg = liquidity_score >= 0.7
    ? 'bg-green-900/30'
    : liquidity_score >= 0.4
      ? 'bg-yellow-900/30'
      : 'bg-red-900/30'

  // Spread health
  const spreadColor = spread_bps <= 5
    ? 'text-green-400'
    : spread_bps <= 25
      ? 'text-yellow-400'
      : 'text-red-400'

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">LIQUIDITY & SLIPPAGE</span>
        <MetricStatusBadge status={status} />
      </div>

      {/* Liquidity Score */}
      <div className={`${liquidityBg} rounded-lg p-3 text-center`}>
        <div className="text-[10px] text-gray-500 uppercase mb-1">Liquidity Score</div>
        <div className={`text-2xl font-bold ${liquidityColor}`}>
          {(liquidity_score * 100).toFixed(0)}%
        </div>
        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden mt-2">
          <div
            className={`h-full ${liquidityColor.replace('text-', 'bg-')}`}
            style={{ width: `${liquidity_score * 100}%` }}
          />
        </div>
      </div>

      {/* Spread Badge */}
      <div className="bg-gray-900/50 rounded p-2">
        <div className="flex justify-between items-center">
          <span className="text-xs text-gray-500">Spread</span>
          <span className={`font-mono text-sm ${spreadColor}`}>
            {spread_bps.toFixed(1)} bps
          </span>
        </div>
      </div>

      {/* Depth Badges */}
      <div className="grid grid-cols-3 gap-1 text-xs">
        {['10bp', '25bp', '50bp'].map((key) => (
          <div key={key} className="bg-gray-900/50 rounded p-1.5 text-center">
            <div className="text-[9px] text-gray-500">{key}</div>
            <div className="font-mono text-[10px]">
              ${formatNumber(depth_usd[key] || 0, 0)}
            </div>
          </div>
        ))}
      </div>

      {/* Slippage Estimates */}
      <div className="space-y-1">
        <div className="text-[10px] text-gray-500 uppercase">Est. Slippage</div>
        <div className="grid grid-cols-3 gap-1 text-xs">
          {['1000', '5000', '10000'].map((size) => {
            const impact = impact_est_bps[size] || 0
            const impactColor = impact <= 5 ? 'text-green-400' : impact <= 15 ? 'text-yellow-400' : 'text-red-400'
            return (
              <div key={size} className="bg-gray-900/50 rounded p-1.5 text-center">
                <div className="text-[9px] text-gray-500">${formatNumber(Number(size), 0)}</div>
                <div className={`font-mono text-[10px] ${impactColor}`}>
                  {impact.toFixed(1)} bps
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Heatmap (simplified bar list) */}
      {book_heatmap && book_heatmap.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] text-gray-500 uppercase">Book Heatmap (Top Levels)</div>
          <div className="space-y-0.5 max-h-32 overflow-y-auto">
            {book_heatmap.slice(0, 10).map((level, i) => {
              const maxSize = Math.max(...book_heatmap.map((l) => l.size_usd))
              const widthPct = (level.size_usd / maxSize) * 100
              return (
                <div key={i} className="flex items-center gap-1 text-[9px]">
                  <span className="w-16 text-gray-500 font-mono text-right">
                    ${level.price.toLocaleString()}
                  </span>
                  <div className="flex-1 h-2 bg-gray-800 rounded overflow-hidden">
                    <div
                      className={`h-full ${level.side === 'bid' ? 'bg-green-600' : 'bg-red-600'}`}
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                  <span className={`w-12 text-right font-mono ${level.side === 'bid' ? 'text-green-400' : 'text-red-400'}`}>
                    ${formatNumber(level.size_usd, 0)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
