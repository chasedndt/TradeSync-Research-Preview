// Regime badge
export function RegimeBadge({ regime }: { regime: string }) {
  const colors: Record<string, string> = {
    extreme_positive: 'bg-red-900/50 text-red-400',
    elevated_positive: 'bg-orange-900/50 text-orange-400',
    neutral: 'bg-gray-800 text-gray-400',
    elevated_negative: 'bg-blue-900/50 text-blue-400',
    extreme_negative: 'bg-cyan-900/50 text-cyan-400',
    build: 'bg-green-900/50 text-green-400',
    unwind: 'bg-red-900/50 text-red-400',
    flat: 'bg-gray-800 text-gray-400',
    high: 'bg-purple-900/50 text-purple-400',
    normal: 'bg-gray-800 text-gray-400',
    low: 'bg-yellow-900/50 text-yellow-400',
  }

  return (
    <span className={`text-xs px-2 py-0.5 rounded ${colors[regime] || 'bg-gray-800 text-gray-400'}`}>
      {regime.replace('_', ' ').toUpperCase()}
    </span>
  )
}
