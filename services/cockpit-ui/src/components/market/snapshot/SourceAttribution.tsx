import type { MarketSnapshot } from '../../../api/types'

interface SourceAttributionProps {
  activeSnapshot: MarketSnapshot
}

/** Which provider supplied which metrics, and when the snapshot was updated. Moved out of pages/Market.tsx unchanged. */
export function SourceAttribution({ activeSnapshot }: SourceAttributionProps) {
  // Source Attribution
  return (
    <div className="card bg-gray-900/30 text-xs text-gray-500">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-gray-400">Sources: </span>
          {activeSnapshot.sources.map((s, i) => (
            <span key={i}>
              {s.provider} ({s.metrics_provided.join(', ')})
              {i < activeSnapshot.sources.length - 1 ? ', ' : ''}
            </span>
          ))}
        </div>
        <div className="text-gray-600">
          Updated: {new Date(activeSnapshot.ts).toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}
