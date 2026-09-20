import { useState } from 'react'
import { useReviewQuarantineItem } from '../api/hooks/useQuarantine'
import type { QuarantineItem } from '../api/types'
import { extractionLine, summarise } from './IntakeSummary'

const PROVENANCE_OPTIONS = [
  { value: 'context_only', label: 'Context only', scoreable: false },
  { value: 'proxy', label: 'Proxy', scoreable: false },
  { value: 'derived', label: 'Derived', scoreable: true },
  { value: 'observed', label: 'Observed', scoreable: true },
]

export function IntakeRow({ item }: { item: QuarantineItem }) {
  const [provenance, setProvenance] = useState('context_only')
  const review = useReviewQuarantineItem()
  const s = summarise(item)
  const x = extractionLine(item)
  const decided = Boolean(item.reviewed_by)
  const when = new Date(item.observed_at ?? item.received_at)

  return (
    <details className="panel" style={{ padding: '10px 12px' }}>
      <summary style={{ cursor: 'pointer', display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr) auto', gap: 12, alignItems: 'baseline' }}>
        <span className={`pill ${item.accepted ? 'pill--good' : 'pill--bad'}`}>{item.accepted ? item.source : 'refused'}</span>
        <span style={{ minWidth: 0 }}>
          <strong style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</strong>
          <span className="metric-sub" style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {s.who} · {s.body.split('\n')[0].slice(0, 160)}
          </span>
        </span>
        <span style={{ textAlign: 'right' }}>
          <span className="metric-sub" style={{ display: 'block' }}>{when.toUTCString().slice(5, 22)}</span>
          <span className={`metric-sub ${x.tone}`} style={{ display: 'block' }}>{x.text.slice(0, 70)}</span>
        </span>
      </summary>

      <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
        <p style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.5, maxHeight: 360, overflowY: 'auto' }}>{s.body}</p>
        {s.extra.length > 0 && <span className="metric-sub">{s.extra.join(' · ')}</span>}
        <span className={`metric-sub ${x.tone}`}>Extraction: {x.text}</span>

        {item.reasons.length > 0 && (
          <div>
            <span className="pipeline-detail-label">Refused because</span>
            <ul>{item.reasons.map((r) => <li key={r.code}><code>{r.code}</code> — {r.detail}</li>)}</ul>
          </div>
        )}

        <details>
          <summary className="metric-sub" style={{ cursor: 'pointer' }}>raw submission · digest {item.content_digest.slice(0, 16)}…</summary>
          <pre style={{ overflowX: 'auto', fontSize: 11, margin: '4px 0 0', maxHeight: 220 }}>{JSON.stringify(item.payload, null, 2)}</pre>
        </details>

        {item.accepted && !item.promoted_to && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <label className="metric-sub" htmlFor={`prov-${item.id}`}>Promote as</label>
            <select id={`prov-${item.id}`} value={provenance} onChange={(e) => setProvenance(e.target.value)}>
              {PROVENANCE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}{o.scoreable ? '' : ' (cannot score)'}</option>)}
            </select>
            <button type="button" className="chip" disabled={review.isPending}
              onClick={() => review.mutate({ id: item.id, reviewedBy: 'operator', promote: true, targetProvenance: provenance })}>
              {review.isPending ? 'Recording…' : 'Review & promote'}
            </button>
            <button type="button" className="chip" disabled={review.isPending}
              onClick={() => review.mutate({ id: item.id, reviewedBy: 'operator', promote: false, targetProvenance: provenance })}>
              Mark reviewed only
            </button>
            {decided && <span className="metric-sub">reviewed by {item.reviewed_by}</span>}
          </div>
        )}
        {item.promoted_to && <span className="pill pill--warn">promoted · {item.promoted_to}</span>}

        {review.data && review.data.blockers.length > 0 && (
          <div className="tone-warn">
            <span className="pipeline-detail-label">Promotion blocked</span>
            <ul>{review.data.blockers.map((b) => <li key={b.code}><code>{b.code}</code> — {b.detail}</li>)}</ul>
          </div>
        )}
      </div>
    </details>
  )
}
