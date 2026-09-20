import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { WalletChange, WalletChangeResult, WalletRegistry } from '../walletRegistryTypes'

const KEY = ['wallet-registry']

export function useWalletRegistry() {
  return useQuery({ queryKey: KEY, queryFn: () => apiGet<WalletRegistry>('/state/wallets'), staleTime: 15_000, retry: 1 })
}

export function useAddWallet() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (change: WalletChange) => apiPost<WalletChangeResult>('/state/wallets', change),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDisconnectWallet() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, operator, reason }: { id: string; operator: string; reason: string }) =>
      apiPost<WalletChangeResult>(`/state/wallets/${encodeURIComponent(id)}/disconnect`, { operator, reason }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  })
}
