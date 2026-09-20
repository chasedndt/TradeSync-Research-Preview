// Format large numbers
export function formatNumber(n: number, decimals = 2): string {
  if (Math.abs(n) >= 1_000_000_000) return (n / 1_000_000_000).toFixed(decimals) + 'B'
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(decimals) + 'M'
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(decimals) + 'K'
  return n.toFixed(decimals)
}

// Format percentage
export function formatPct(n: number, decimals = 2): string {
  return (n * 100).toFixed(decimals) + '%'
}
