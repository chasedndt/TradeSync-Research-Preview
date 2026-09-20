import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useEdition, useEditions } from '../../api/hooks/useEditions'
import { BriefingCard } from './BriefingCard'
import { ComprehensiveMarketBrief } from './ComprehensiveMarketBrief'
import { hasBriefing, hasOutlook } from './guards'
import { KeyEvents } from './KeyEvents'
import { InteractiveThesisPlayer } from './InteractiveThesisPlayer'
import { RegenerateControl } from './RegenerateControl'
import { SymbolGrid } from './SymbolGrid'
import styles from './Thesis.module.css'

/**
 * The market thesis as a trader reads it: the outlook first (lean, lead
 * reads, notes), then this week's events with measured reactions and
 * coverage, the Hermes briefing, every market as a card, and the narration.
 */
export function EditionView() {
  const [params, setParams] = useSearchParams()
  const list = useEditions(50)
  const [selected, setSelected] = useState<string | null>(() => params.get('edition'))
  const latest = list.data?.editions[0]
  const id = selected ?? latest?.id ?? null
  const full = useEdition(id)
  const e = full.data

  useEffect(() => {
    const requested = params.get('edition')
    if (requested !== selected) setSelected(requested)
  }, [params, selected])

  const chooseEdition = (editionId: string) => {
    setSelected(editionId)
    const next = new URLSearchParams(params)
    next.set('edition', editionId)
    setParams(next, { replace: true })
  }

  const when = e ? new Date(e.generated_at).toUTCString().slice(0, 22) + ' UTC' : ''
  const next = list.data?.schedule.next

  return (
    <div className={styles.edition}>
      <section className="panel">
        <div className={styles.head}>
          <div>
            <h2>Market Thesis</h2>
            <p>
              {e ? `${e.edition.replace('-', ' ')} edition · ${when}${e.reason ? ` · reason: ${e.reason}` : ''}` : list.isLoading ? 'loading…' : 'no edition yet'}
              {next?.at ? ` · next scheduled ${next.edition} at ${new Date(next.at).toUTCString().slice(17, 22)} UTC` : ''}
            </p>
          </div>
          <RegenerateControl />
        </div>
        {(list.data?.editions.length ?? 0) > 1 && <details className={styles.archive}>
          <summary><span><strong>Brief archive</strong><small>{list.data!.editions.length} most recent frozen editions · current selection stays expanded above</small></span><span>Browse ↓</span></summary>
          <div className={styles.archiveList}>{list.data!.editions.map((ed) => (
            <button key={ed.id} type="button" className={ed.id === id ? styles.archiveActive : ''} onClick={() => chooseEdition(ed.id)} title={ed.headline}>
              <span><strong>{ed.edition.replace('-', ' ')}</strong><small>{new Date(ed.generated_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</small></span>
              <span>{ed.id === id ? 'Viewing' : 'Open'} →</span>
            </button>
          ))}</div>
        </details>}
        {e && !hasOutlook(e.outlook) && <p className="tone-dim" style={{ padding: '0 18px 14px' }}>This edition predates the market outlook. Regenerate to build one.</p>}
        {full.isError && <p className="tone-bad" style={{ padding: '0 18px 14px' }}>Edition unavailable.</p>}
      </section>

      {e && e.media.audio && <InteractiveThesisPlayer edition={e} />}

      {e && hasOutlook(e.outlook) && <ComprehensiveMarketBrief edition={e} outlook={e.outlook} />}

      {e && hasOutlook(e.outlook) && (
        <div className={styles.twoCol}>
          <section className="panel">
            <div className="panel-heading"><div><h3>This week</h3><p>scheduled events · how the market reacted to past releases · recent coverage</p></div></div>
            <div className={styles.sectionBody}><KeyEvents events={e.outlook.key_events} method={e.outlook.reaction_method} /></div>
          </section>
          <BriefingCard b={hasBriefing(e.briefing) ? e.briefing : null} />
        </div>
      )}

      {e?.theses && (
        <section className="panel">
          <div className="panel-heading"><div><h3>Markets</h3><p>every tracked market's thesis at this edition</p></div></div>
          <SymbolGrid theses={e.theses} order={e.symbols} />
        </section>
      )}

      {e && (
        <section className={`panel ${styles.script}`}>
          <details>
            <summary>Written edition and spoken script</summary>
            <pre>{e.text}</pre>
            <pre>{e.narration}</pre>
          </details>
        </section>
      )}
    </div>
  )
}
