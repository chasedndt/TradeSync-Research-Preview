import { formatNumber, formatPct } from './snapshotFormat'
import type { MarketSnapshot } from '../../../api/types'

interface MultiVenueGridProps {
  filteredSnapshots: MarketSnapshot[]
  setSelectedVenue: (venue: string) => void
  setSelectedSymbol: (symbol: string) => void
}

/** One comparison card per venue when every venue is selected. Moved out of pages/Market.tsx unchanged. */
export function MultiVenueGrid({ filteredSnapshots, setSelectedVenue, setSelectedSymbol }: MultiVenueGridProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {filteredSnapshots.map((snap) => (
        <div key={`${snap.venue}-${snap.symbol}`} className="card border border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <div>
              <span className="text-sm font-bold capitalize">{snap.venue}</span>
              <span className="text-xs text-gray-500 ml-2">{snap.symbol}</span>
            </div>
            <div className="flex items-center gap-2">
              {(snap.snapshot_age_ms ?? 0) > 60000 && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-900/50 text-red-400 border border-red-700">STALE</span>
              )}
              <span className="text-[9px] text-gray-500">{new Date(snap.ts).toLocaleTimeString()}</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500 mb-1">Funding</div>
              {snap.funding ? (
                <div className="font-mono">{formatPct(snap.funding.horizons.now, 4)}</div>
              ) : <div className="text-gray-600">—</div>}
            </div>
            <div className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500 mb-1">OI</div>
              {snap.oi ? (
                <div className="font-mono">${formatNumber(snap.oi.current_usd)}</div>
              ) : <div className="text-gray-600">—</div>}
            </div>
            <div className="bg-gray-900/50 rounded p-2">
              <div className="text-gray-500 mb-1">Regime</div>
              {snap.regimes ? (
                <div className={`font-medium ${
                  snap.regimes.trend === 'bullish' ? 'text-green-400' :
                  snap.regimes.trend === 'bearish' ? 'text-red-400' : 'text-yellow-400'
                }`}>{snap.regimes.trend?.toUpperCase() || 'N/A'}</div>
              ) : <div className="text-gray-600">—</div>}
            </div>
          </div>
          <button
            onClick={() => { setSelectedVenue(snap.venue); setSelectedSymbol(snap.symbol) }}
            className="mt-3 w-full text-[10px] text-blue-500 hover:text-blue-400 text-center"
          >
            View detailed panels →
          </button>
        </div>
      ))}
    </div>
  )
}
