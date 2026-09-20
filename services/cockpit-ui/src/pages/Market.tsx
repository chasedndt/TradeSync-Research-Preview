import { useState } from 'react'
import { LiquidationMap } from '../components/market/LiquidationMap'
import { LiquidityHeatmap } from '../components/market/LiquidityHeatmap'
import { LiquidationsPanel } from '../components/market/liquidations/LiquidationsPanel'
import { RegimeSummaryPanel } from '../components/market/regime/RegimeSummaryPanel'
import { MarketFilters } from '../components/market/snapshot/MarketFilters'
import { MarketStatusBanners } from '../components/market/snapshot/MarketStatusBanners'
import { MultiVenueGrid } from '../components/market/snapshot/MultiVenueGrid'
import { SnapshotPanels } from '../components/market/snapshot/SnapshotPanels'
import { SourceAttribution } from '../components/market/snapshot/SourceAttribution'
import type { WithDerived } from '../api/liquidationSourceTypes'
import { useMarketSnapshots, useMarketStatus } from '../api/hooks'
import type { MarketSnapshot } from '../api/types'

// Main Market Page
export function Market() {
  const { data, isLoading, error, refetch, isFetching } = useMarketSnapshots()
  const { data: statusData } = useMarketStatus()
  const [selectedVenue, setSelectedVenue] = useState<string>('all')
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTC-PERP')

  const snapshots = data?.snapshots || []

  // Filter snapshots
  const filteredSnapshots = snapshots.filter((s) => {
    if (selectedVenue !== 'all' && s.venue !== selectedVenue) return false
    if (selectedSymbol !== 'all' && s.symbol !== selectedSymbol) return false
    return true
  })

  // Get unique venues and symbols
  const venues = ['all', ...new Set(snapshots.map((s) => s.venue))]
  const symbols = ['all', ...new Set(snapshots.map((s) => s.symbol))]

  // Single-venue view: first match. Multi-venue view: all filtered snapshots.
  const activeSnapshot = filteredSnapshots[0]
  const isMultiVenue = selectedVenue === 'all' && filteredSnapshots.length > 1

  // Check if service is available
  const serviceAvailable = statusData?.providers && statusData.providers.length > 0

  return (
    <div className="space-y-6">
      <MarketFilters
        venues={venues}
        symbols={symbols}
        selectedVenue={selectedVenue}
        selectedSymbol={selectedSymbol}
        setSelectedVenue={setSelectedVenue}
        setSelectedSymbol={setSelectedSymbol}
        refetch={refetch}
        isFetching={isFetching}
      />

      <MarketStatusBanners
        serviceAvailable={serviceAvailable}
        isLoading={isLoading}
        error={error}
        filteredSnapshots={filteredSnapshots}
        isMultiVenue={isMultiVenue}
        selectedSymbol={selectedSymbol}
      />

      {/* Multi-venue comparison grid */}
      {isMultiVenue && (
        <MultiVenueGrid
          filteredSnapshots={filteredSnapshots}
          setSelectedVenue={setSelectedVenue}
          setSelectedSymbol={setSelectedSymbol}
        />
      )}

      {/* Main Content — single-venue detailed panels */}
      {activeSnapshot && !isMultiVenue && (
        <>
          <SnapshotPanels activeSnapshot={activeSnapshot} />

          <RegimeSummaryPanel symbol={activeSnapshot.symbol} />
          <LiquidationsPanel
            symbol={activeSnapshot.symbol}
            snapshot={activeSnapshot as MarketSnapshot & WithDerived}
            onRefresh={() => void refetch()}
            refreshing={isFetching}
          />
          <LiquidityHeatmap symbol={activeSnapshot.symbol} />
          <LiquidationMap symbol={activeSnapshot.symbol} />

          <SourceAttribution activeSnapshot={activeSnapshot} />
        </>
      )}
    </div>
  )
}
