import { AlertCircle, TrendingUp, Percent, BarChart3, Activity, Droplets } from 'lucide-react'
import { FundingPanel } from './FundingPanel'
import { OIPanel } from './OIPanel'
import { VolumePanel } from './VolumePanel'
import { OrderbookPanel } from './OrderbookPanel'
import { LiquidityPanel } from './LiquidityPanel'
import type { MarketSnapshot, MarketSnapshotWithMicrostructure } from '../../../api/types'

interface SnapshotPanelsProps {
  activeSnapshot: MarketSnapshot
}

/** The data age banner and the grid of metric panels for one venue and symbol. Moved out of pages/Market.tsx unchanged. */
export function SnapshotPanels({ activeSnapshot }: SnapshotPanelsProps) {
  return (
    <>
      {/* Data Age Banner: snapshot_age_ms is the snapshot's liveness; data_age_ms is its oldest metric and never refreshes. */}
      {(activeSnapshot.snapshot_age_ms ?? 0) > 60000 && (
        <div className="bg-red-900/30 border border-red-700/50 rounded-lg px-4 py-2 flex items-center gap-2 text-red-400 text-sm">
          <AlertCircle size={16} />
          Market data last updated {Math.floor((activeSnapshot.snapshot_age_ms ?? 0) / 1000)}s ago
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Funding Regime */}
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-green-900/20 rounded">
              <Percent size={20} className="text-green-500" />
            </div>
            <div>
              <h3 className="font-medium">Funding Regime</h3>
              <p className="text-xs text-gray-500">{activeSnapshot.venue} / {activeSnapshot.symbol}</p>
            </div>
          </div>
          <FundingPanel snapshot={activeSnapshot} />
        </div>

        {/* Open Interest */}
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-blue-900/20 rounded">
              <BarChart3 size={20} className="text-blue-500" />
            </div>
            <div>
              <h3 className="font-medium">Open Interest</h3>
              <p className="text-xs text-gray-500">OI changes and delta tracking</p>
            </div>
          </div>
          <OIPanel snapshot={activeSnapshot} />
        </div>

        {/* Volume Profile */}
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-purple-900/20 rounded">
              <Activity size={20} className="text-purple-500" />
            </div>
            <div>
              <h3 className="font-medium">Volume Summary</h3>
              <p className="text-xs text-gray-500">24h volume and cumulative delta</p>
            </div>
          </div>
          <VolumePanel snapshot={activeSnapshot} />
        </div>

        {/* Spread & Depth */}
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-orange-900/20 rounded">
              <TrendingUp size={20} className="text-orange-500" />
            </div>
            <div>
              <h3 className="font-medium">Spread & Depth</h3>
              <p className="text-xs text-gray-500">Orderbook liquidity</p>
            </div>
          </div>
          <OrderbookPanel snapshot={activeSnapshot} />
        </div>

        {/* Phase 3C: Liquidity & Slippage */}
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-teal-900/20 rounded">
              <Droplets size={20} className="text-teal-500" />
            </div>
            <div>
              <h3 className="font-medium">Liquidity & Slippage</h3>
              <p className="text-xs text-gray-500">Microstructure analysis</p>
            </div>
          </div>
          <LiquidityPanel snapshot={activeSnapshot as MarketSnapshotWithMicrostructure} />
        </div>
      </div>
    </>
  )
}
