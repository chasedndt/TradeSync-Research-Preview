import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPut } from '../client'
import type { WalletConnectSaveResult, WalletConnectSettings } from '../walletConnectSettingsTypes'

const KEY = ['walletconnect-settings']

/** The saved public WalletConnect project ID, if any, with who saved it and when. */
export function useWalletConnectSettings() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiGet<WalletConnectSettings>('/state/settings/walletconnect'),
    staleTime: 60_000,
    retry: 1,
  })
}

/** Save the project ID, or clear it with an empty one; state-api keeps an audit row for each change. */
export function useSaveWalletConnectSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (change: { project_id: string; changed_by: string }) =>
      apiPut<WalletConnectSaveResult>('/state/settings/walletconnect', change),
    onSuccess: (result) => queryClient.setQueryData(KEY, result),
  })
}
