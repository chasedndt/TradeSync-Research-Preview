import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../api/client'
import type { QuarantineList } from '../api/types'
import { TradingViewSetup } from '../components/intake/TradingViewSetup'
import { IntakeRow } from './IntakeRow'
import { summarise } from './IntakeSummary'

const SOURCES: { key: string | null; label: string }[] = [
  { key: null, label: 'All' },
  { key: 'tradingview', label: 'Pine alerts' },
  { key: 'discord', label: 'Discord posts' },
  { key: 'chaseos', label: 'Hermes jobs' },
  { key: 'agent_harness', label: 'Harness answers' },
]

function useIntake(source: string | null, pendingOnly: boolean, limit: number) {
  return useQuery({
    queryKey: ['intake', source ?? 'all', pendingOnly, limit],
    queryFn: () => apiGet<QuarantineList>(`/state/quarantine?limit=${limit}&pending_only=${pendingOnly}${source ? `&source=${source}` : ''}`),
    refetchInterval: 30_000,
    retry: 1,
  })
}

/**
 * Knowledge intake: what every Tier B connector sent, read as a person would
 * read it, with what extraction made of each item. Nothing here is evidence.
 * Material sits in quarantine until a human promotes it, and promotion never
 * grants scoring or execution authority.
 */
export function KnowledgeIntake() {
  const [pendingOnly, setPendingOnly] = useState(false)
  const [source, setSource] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const { data, isLoading, isError } = useIntake(source, pendingOnly, 200)

  const items = useMemo(() => {
    const q = query.trim().toLowerCase()
    const all = data?.items ?? []
    if (!q) return all
    return all.filter((i) => {
      const s = summarise(i)
      return `${s.title} ${s.who} ${s.body}`.toLowerCase().includes(q)
    })
  }, [data, query])

  const tally = useMemo(() => {
    const t = { held: items.length, claims: 0, noClaim: 0, unread: 0, refused: 0 }
    for (const i of items) {
      if (!i.accepted) t.refused += 1
      const x = i.extraction
      const n = (x?.rule?.claims ?? 0) + (x?.harness?.claims ?? 0)
      if (!x || (!x.rule && !x.harness)) t.unread += 1
      else if (n > 0) t.claims += 1
      else t.noClaim += 1
    }
    return t
  }, [items])

  return (
    <div className="page">
      <header className="panel-heading" style={{ marginBottom: 16 }}>
        <div>
          <h2>Knowledge intake</h2>
          <p>
            Everything the connectors sent, held as untrusted material with provenance. Each item shows what the rule reader and the
            harness made of it. Nothing here can score, approve or execute; promotion is an operator act.
          </p>
        </div>
      </header>

      {/* How a TradingView alert gets here, whether its secret is configured, and the latest alerts */}
      <TradingViewSetup />

      <section className="panel" style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
          {SOURCES.map((s) => (
            <button key={s.label} type="button" className={source === s.key ? 'chip chip--active' : 'chip'} onClick={() => setSource(s.key)} aria-pressed={source === s.key}>
              {s.label}
            </button>
          ))}
          <span style={{ width: 1, alignSelf: 'stretch', background: 'var(--border)' }} />
          <button type="button" className={pendingOnly ? 'chip chip--active' : 'chip'} onClick={() => setPendingOnly(!pendingOnly)} aria-pressed={pendingOnly}>
            Awaiting review
          </button>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="filter by text…"
            aria-label="Filter held items"
            style={{ marginLeft: 'auto', background: '#0d1a2a', color: 'var(--text)', border: '1px solid #32445a', borderRadius: 4, padding: '6px 8px', font: '12px var(--font-mono)', minWidth: 180 }}
          />
        </div>

        <div className="metric-sub" style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap' }}>
          <span>{tally.held} held</span>
          <span className="tone-good">{tally.claims} yielded claims</span>
          <span>{tally.noClaim} read, no claim</span>
          <span>{tally.unread} not yet read</span>
          {tally.refused > 0 && <span className="tone-bad">{tally.refused} refused at intake</span>}
        </div>

        {isError ? (
          <p className="tone-bad">Intake unavailable. The State API did not answer; no submissions are inferred.</p>
        ) : isLoading ? (
          <p className="tone-dim">Loading submissions…</p>
        ) : items.length === 0 ? (
          <p className="tone-dim">Nothing held for this filter. Connectors post here; TradeSync never reaches out to collect from them.</p>
        ) : (
          <div style={{ display: 'grid', gap: 8 }}>
            {items.map((item) => <IntakeRow key={item.id} item={item} />)}
          </div>
        )}

        <p className="market-footnote" style={{ marginTop: 14 }}>
          quarantine → extraction → claims measured on the source cards → operator promotion &nbsp;•&nbsp; refused submissions are kept so an attempted misuse stays visible
        </p>
      </section>
    </div>
  )
}
