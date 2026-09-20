import { AlertCircle, RefreshCw } from 'lucide-react'
import type { MarketSnapshot } from '../../../api/types'

interface MarketStatusBannersProps {
  serviceAvailable: boolean | undefined
  isLoading: boolean
  error: Error | null
  filteredSnapshots: MarketSnapshot[]
  isMultiVenue: boolean
  selectedSymbol: string
}

/** Service, loading, error, empty and multi-venue notices above the market panels. Moved out of pages/Market.tsx unchanged. */
export function MarketStatusBanners({ serviceAvailable, isLoading, error, filteredSnapshots, isMultiVenue, selectedSymbol }: MarketStatusBannersProps) {
  return (
    <>
      {/* Service Status Banner */}
      {!serviceAvailable && !isLoading && (
        <div className="bg-yellow-900/30 border border-yellow-700/50 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="text-yellow-500" size={20} />
          <div>
            <div className="font-medium text-yellow-400">Market Data Service Unavailable</div>
            <div className="text-xs text-yellow-600">
              The market-data service is not running. Start it with: docker compose -f ops/compose.full.yml up market-data
            </div>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <RefreshCw size={24} className="animate-spin text-gray-500" />
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-900/30 border border-red-700/50 rounded-lg p-4">
          <div className="font-medium text-red-400">Error loading market data</div>
          <div className="text-xs text-red-600">{String(error)}</div>
        </div>
      )}

      {/* No Data State */}
      {!isLoading && !error && filteredSnapshots.length === 0 && serviceAvailable && (
        <div className="bg-gray-900/50 border border-gray-800 border-dashed rounded-lg p-8 text-center text-gray-500">
          No market snapshots available. Data should appear within 10 seconds of service startup.
        </div>
      )}

      {/* Multi-venue notice when All Venues is selected */}
      {isMultiVenue && (
        <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg px-4 py-2 flex items-center gap-3 text-sm">
          <AlertCircle size={16} className="text-blue-400 flex-shrink-0" />
          <div>
            <span className="text-blue-400 font-medium">Multi-venue view</span>
            <span className="text-blue-600 ml-2">
              Showing {filteredSnapshots.length} venues for {selectedSymbol === 'all' ? 'all symbols' : selectedSymbol}. Values are per-venue — no cross-venue aggregation. Select a specific venue for detailed panels.
            </span>
          </div>
        </div>
      )}
    </>
  )
}
