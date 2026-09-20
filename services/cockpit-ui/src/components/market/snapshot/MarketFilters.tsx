import { RefreshCw, ChevronDown } from 'lucide-react'

interface MarketFiltersProps {
  venues: string[]
  symbols: string[]
  selectedVenue: string
  selectedSymbol: string
  setSelectedVenue: (venue: string) => void
  setSelectedSymbol: (symbol: string) => void
  refetch: () => unknown
  isFetching: boolean
}

/** The venue and symbol filters, and the refresh control for the snapshot reading. Moved out of pages/Market.tsx unchanged. */
export function MarketFilters({ venues, symbols, selectedVenue, selectedSymbol, setSelectedVenue, setSelectedSymbol, refetch, isFetching }: MarketFiltersProps) {
  return (
    <div className="flex items-center justify-between">
      <h2 className="text-xl font-bold">Market Intel</h2>
      <div className="flex items-center gap-3">
        {/* Venue Filter */}
        <div className="relative">
          <select
            value={selectedVenue}
            onChange={(e) => setSelectedVenue(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm appearance-none pr-8"
          >
            {venues.map((v) => (
              <option key={v} value={v}>
                {v === 'all' ? 'All Venues' : v.charAt(0).toUpperCase() + v.slice(1)}
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500" />
        </div>

        {/* Symbol Filter */}
        <div className="relative">
          <select
            value={selectedSymbol}
            onChange={(e) => setSelectedSymbol(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm appearance-none pr-8"
          >
            {symbols.map((s) => (
              <option key={s} value={s}>
                {s === 'all' ? 'All Symbols' : s}
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500" />
        </div>

        {/* Refresh */}
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="p-2 bg-gray-800 rounded hover:bg-gray-700 disabled:opacity-50"
        >
          <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
        </button>
      </div>
    </div>
  )
}
