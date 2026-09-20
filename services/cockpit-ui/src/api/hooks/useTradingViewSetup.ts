import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { TradingViewSetup } from '../tradingViewSetupTypes'

/** The TradingView webhook setup, whether its secret is configured, and the newest receipts. */
export function useTradingViewSetup(limit = 8) {
  return useQuery({
    queryKey: ['tradingview-setup', limit],
    queryFn: () => apiGet<TradingViewSetup>(`/state/tradingview/setup?limit=${limit}`),
    refetchInterval: 30_000,
    retry: 1,
  })
}
