import { useState } from 'react'
import { Check, ShieldCheck, Trash2 } from 'lucide-react'
import { clearOperatorToken, getOperatorToken, OPERATOR_TOKEN_HEADER, setOperatorToken } from '../../api/credentials'
import { useAccessPolicy } from '../../api/hooks/useOperatorSettings'
import { ReadingStamp } from '../ReadingStamp'
import { OperatorTokenGuide } from './OperatorTokenGuide'
import type { TokenState } from './operatorTokenText'

const TOKEN_STATE: Record<TokenState, string> = {
  disabled: 'state-api does not require an operator token. Changes are accepted from this Cockpit and from tools on this machine.',
  required: 'state-api requires the operator token on every change. Without it, saving, pausing or adopting anything is refused.',
  misconfigured: 'state-api refuses every change: STATE_API_OPERATOR_TOKEN is set but shorter than 32 characters.',
}

/** Whether state-api requires the operator token, and the token itself for this browser session. */
export function OperatorAccess() {
  const policy = useAccessPolicy()
  const [tokenInput, setTokenInput] = useState('')
  const [kept, setKept] = useState(() => getOperatorToken() !== null)

  const keep = () => {
    if (!tokenInput.trim()) return
    setOperatorToken(tokenInput)
    setTokenInput('')
    setKept(true)
  }

  const forget = () => {
    clearOperatorToken()
    setKept(false)
  }

  const summary = policy.data
    ? TOKEN_STATE[policy.data.operator_token]
    : policy.isError
      ? 'Access policy unavailable: this state-api build does not report one.'
      : 'Reading the access policy…'

  return (
    <section className="card" aria-label="Operator access">
      <h3 className="text-sm font-medium text-gray-400 mb-4 flex items-center gap-2">
        <ShieldCheck size={14} />
        Operator access
      </h3>
      <p className="text-sm text-gray-300">{summary}</p>
      <ReadingStamp at={policy.dataUpdatedAt || null} onRefresh={() => void policy.refetch()} refreshing={policy.isFetching} />
      {policy.data && (
        <p className="mt-1 text-xs text-gray-500">
          Changes sent from other web pages are {policy.data.origin_check === 'enforced' ? 'refused' : 'accepted: the origin check is switched off'}.
        </p>
      )}
      <OperatorTokenGuide state={policy.data?.operator_token} />
      <label htmlFor="operator-token" className="block text-sm font-medium text-gray-300 mt-4 mb-2">
        Operator token
      </label>
      <div className="flex gap-2">
        <input
          id="operator-token"
          type="password"
          autoComplete="off"
          value={tokenInput}
          onChange={(e) => setTokenInput(e.target.value)}
          placeholder={kept ? 'Kept for this browser session' : 'Paste the operator token'}
          className="input flex-1"
        />
        <button onClick={keep} disabled={!tokenInput.trim()} className="btn btn-primary flex items-center gap-2">
          <Check size={16} />
          Keep
        </button>
        {kept && (
          <button onClick={forget} className="px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-400" title="Forget the operator token" aria-label="Forget the operator token">
            <Trash2 size={16} />
          </button>
        )}
      </div>
      <p className="mt-2 text-xs text-gray-500">
        Sent as {OPERATOR_TOKEN_HEADER} to this Cockpit&apos;s state-api only. Kept for this browser session, never on disk or in the
        Cockpit build, so enter it again after closing the browser. To paste it without displaying it, run
        tools/copy-runtime-secret.ps1 -Name STATE_API_OPERATOR_TOKEN, then clear the clipboard.
      </p>
    </section>
  )
}
