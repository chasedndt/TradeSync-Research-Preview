import type { MetricStatus } from '../../../api/types'

// Status badge component with truthful states
export function MetricStatusBadge({ status, note }: { status: MetricStatus; note?: string }) {
  const colors: Record<MetricStatus, string> = {
    REAL: 'bg-green-900/50 text-green-400 border-green-700',
    PROXY: 'bg-yellow-900/50 text-yellow-400 border-yellow-700',
    UNAVAILABLE: 'bg-gray-900/50 text-gray-500 border-gray-700',
    STALE: 'bg-red-900/50 text-red-400 border-red-700',
  }

  return (
    <span
      className={`text-[9px] px-1.5 py-0.5 rounded border ${colors[status]}`}
      title={note || status}
    >
      {status}
    </span>
  )
}
