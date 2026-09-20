import { useMemo, useState } from 'react'
import { Filter, Search } from 'lucide-react'
import { useOpportunityBriefs } from '../../api/hooks/useOpportunityBriefs'
import { OpportunityCard } from '../OpportunityCard'
import { QuietState } from '../home/QuietState'
import { readLine } from '../opportunity/brief/briefText'
import styles from './OpportunityList.module.css'

/**
 * Opportunities by status, each card read from its stored brief. The API reports
 * status as it is now: "new" holds only opportunities still inside their TTL, and
 * "expired" holds the rest, so no age filter is applied here.
 */
const statusOptions = [
  { value: 'new', label: 'Live' },
  { value: 'previewed', label: 'Previewed' },
  { value: 'executed', label: 'Executed' },
  { value: 'expired', label: 'Expired' },
]
const timeframeOptions = ['all', '1m', '5m', '15m', '1h', '4h', '1d']

export function OpportunityList() {
  const [status, setStatus] = useState('new')
  const [timeframe, setTimeframe] = useState('all')
  const [search, setSearch] = useState('')
  const [dedup, setDedup] = useState(true)

  const query = useOpportunityBriefs(status, 100)
  // A page kept from the previous status is shown only as that status, never as this one.
  const current = query.data?.status === status ? query.data : undefined

  const filtered = useMemo(() => {
    let list = (current?.briefs ?? []).filter((brief) =>
      (timeframe === 'all' || brief.timeframe === timeframe)
      && brief.symbol.toLowerCase().includes(search.toLowerCase()))
    if (dedup) {
      // The API lists newest first, so the first of each market, timeframe and side is its newest.
      const seen = new Set<string>()
      list = list.filter((brief) => {
        const key = `${brief.symbol}-${brief.timeframe}-${brief.side}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
    }
    return list
  }, [current, timeframe, search, dedup])

  const unfiltered = timeframe === 'all' && search === ''

  return (
    <div className={styles.list}>
      <div className={styles.toolbar}>
        <div className={styles.statuses} role="group" aria-label="Opportunity status">
          {statusOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={status === option.value}
              onClick={() => setStatus(option.value)}
              className={status === option.value ? 'chip chip--active' : 'chip'}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className={styles.reading}>
          {current && <span>{readLine(current.read_at_s)}</span>}
          <button type="button" className="chip" onClick={() => void query.refetch()} disabled={query.isFetching}>
            {query.isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className={styles.filters}>
        <label className={styles.search}>
          <Search className={styles.searchIcon} size={15} aria-hidden="true" />
          <input
            type="text"
            aria-label="Search symbol"
            placeholder="Search symbol, for example BTC"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={`input ${styles.searchInput}`}
          />
        </label>
        <label className={styles.filter}>
          <Filter size={15} aria-hidden="true" />
          Timeframe
          <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className="input">
            {timeframeOptions.map((tf) => <option key={tf} value={tf}>{tf === 'all' ? 'All' : tf}</option>)}
          </select>
        </label>
        <label className={styles.check}>
          <input type="checkbox" checked={dedup} onChange={(e) => setDedup(e.target.checked)} />
          Newest only, per market, timeframe and side
        </label>
      </div>

      {query.isLoading && <p className={styles.message}>Reading opportunities…</p>}
      {query.isError && <p className={styles.error}>Opportunities unavailable: {(query.error as Error).message}</p>}

      {current && filtered.length === 0 && (
        status === 'new' && unfiltered ? (
          <section className="panel" aria-label="No live opportunity">
            <QuietState />
          </section>
        ) : (
          <p className={styles.empty}>No opportunities match these filters.</p>
        )
      )}

      {filtered.length > 0 && (
        <div className={styles.grid}>
          {filtered.map((brief) => <OpportunityCard key={brief.id} brief={brief} />)}
        </div>
      )}
      {current && <p className={styles.note}>{current.note}</p>}
    </div>
  )
}
