import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useHealth, useIntegrationPipeline } from '../../api/hooks'
import { ReadingStamp } from '../ReadingStamp'
import { CACHED_STATE_KEYS, fetchCensus } from './settingsText'
import { StandingRow } from './StandingRow'
import styles from './SettingsPanels.module.css'

/**
 * What this Cockpit and its connections report about themselves: the readings it
 * holds and which are failing, the state API's own health, and any feed that has
 * logged an error. Clearing cached previews is the one repair offered, because it
 * is the one this browser can make.
 */
export function Diagnostics() {
  const client = useQueryClient()
  const health = useHealth()
  const pipeline = useIntegrationPipeline()
  const [countedAt, setCountedAt] = useState(() => Date.now())

  const queries = client.getQueryCache().getAll()
  const failing = queries.filter((query) => query.state.status === 'error')
  const feedErrors = (pipeline.data?.feeds?.feeds ?? []).filter((feed) => feed.last_error)

  const clearCached = () => {
    for (const key of CACHED_STATE_KEYS) {
      try { localStorage.removeItem(key) } catch { /* storage refused: nothing was cached */ }
    }
    window.location.reload()
  }

  return (
    <section className="panel" aria-labelledby="diagnostics-title">
      <div className="panel-heading">
        <div>
          <h3 id="diagnostics-title">Diagnostics</h3>
          <p>What this Cockpit and its connections report about themselves.</p>
        </div>
        <ReadingStamp
          at={countedAt}
          onRefresh={() => { setCountedAt(Date.now()); void health.refetch(); void pipeline.refetch() }}
          refreshing={health.isFetching || pipeline.isFetching}
        />
      </div>
      <div className={styles.body}>
        <dl className={styles.standings}>
          <StandingRow name="Cockpit readings" standing={fetchCensus(queries.length, failing.length)} />
          <div>
            <dt>State API</dt>
            <dd className={`${styles.value} tone-${health.data?.postgres ? 'good' : 'bad'}`}>
              {health.data ? `${health.data.status} · database read in ${health.data.latency_ms.toFixed(0)} ms` : health.isError ? 'not answering' : 'checking…'}
            </dd>
          </div>
          <div>
            <dt>Feeds with an error since start</dt>
            <dd className={`${styles.value} tone-${feedErrors.length ? 'warn' : 'good'}`}>
              {feedErrors.length ? feedErrors.map((feed) => feed.label).join(', ') : 'none'}
            </dd>
          </div>
        </dl>
        {failing.length > 0 && (
          <ul className={styles.list}>
            {failing.map((query) => (
              <li key={query.queryHash} className={styles.note}>
                <strong>{query.queryKey.map(String).join(' · ')}</strong>: {(query.state.error as Error | null)?.message ?? 'no reason given'}
              </li>
            ))}
          </ul>
        )}
        <div className={styles.inline}>
          <button type="button" className="chip" onClick={clearCached}>Clear cached previews and reload</button>
          <span className={styles.note}>Removes the preview and execution results this browser cached. Nothing on the server changes.</span>
        </div>
      </div>
    </section>
  )
}
