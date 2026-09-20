import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../../../api/client'
import { Cell, bps, byStrength, chance, count, heldOut, horizon, polarity, ratio, rule, verdict } from './comparisonFormat'
import styles from './EntryEvidenceComparison.module.css'

type Report = {
  status?: string
  computed_at?: string | null
  cells: Cell[]
  family?: { version: string; sha256: string; rule: string }
  costs?: { total_pct: number; source: string }
  holm?: { cells: number; cells_tested: number; first_rank_bar: number | null }
  population?: { cases: number; symbols: string[]; horizons: number[]; context_coverage: Record<string, number> }
  population_source?: {
    population: string; why: string; window_days: number; opportunities: number
    recorded_history_begins: Record<string, string | null>
    coverage: { no_recorded_book: number; no_open_interest_pair: number; no_liquidation_received: number; no_timeframe_measurement: number; sources: Record<string, string> }
  }
  managed_paper?: { positions: number; note: string }
  minimum_independent_windows?: number
  note?: string
}

export function EntryEvidenceComparison() {
  const query = useQuery({
    queryKey: ['entry-evidence-comparison'],
    queryFn: () => apiGet<Report>('/state/research/entry-evidence-comparison'),
    refetchInterval: 60000,
  })
  const data = query.data
  const cells = data?.cells ?? []
  const tested = cells.filter((cell) => cell.tested)
  const selecting = tested.filter((cell) => cell.selects)

  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="entry-evidence-comparison-title">
      <h3 id="entry-evidence-comparison-title">Does the evidence frozen at entry pick the better calls?</h3>
      <p>
        Six readings taken before each call — resting liquidity near price, the largest wall on each side, which side was
        liquidated in the hour before, the open-interest change over that hour, the funding the position would receive, and
        the measured timeframe lean — each tested in both polarities at every horizon. The comparisons were declared before
        they were run. Research only: nothing here changes a weight, a rule or a permission.
      </p>

      {query.isLoading && <p>Loading the comparison…</p>}
      {query.isError && <p role="alert">Comparison unavailable. No result is substituted for it.</p>}
      {data?.status === 'computing' && <p role="status">Measuring every cell for the first time since the API started.</p>}

      {data && cells.length > 0 && (
        <>
          <div className={styles.metrics}>
            <div><span>calls measured</span><strong>{count(data.population?.cases)}</strong></div>
            <div><span>cells declared</span><strong>{count(data.holm?.cells)}</strong></div>
            <div><span>cells testable</span><strong>{count(data.holm?.cells_tested)}</strong></div>
            <div><span>cells that select</span><strong>{count(selecting.length)}</strong></div>
            <div><span>family bar (best rank)</span><strong>{chance(data.holm?.first_rank_bar)}</strong></div>
            <div><span>round trip cost</span><strong>{bps(data.costs?.total_pct)}</strong></div>
          </div>

          {selecting.length === 0 && (
            <p>
              No cell selects at the family&rsquo;s bar. With {count(data.holm?.cells)} comparisons looked at together, a
              single cell clearing an unadjusted bar would be expected from noise alone, so the bar counts all of them.
            </p>
          )}

          <div className={styles.scroll}>
            <table>
              <thead>
                <tr>
                  <th>Reading</th><th>Polarity</th><th>Horizon</th>
                  <th className={styles.numeric}>With reading</th>
                  <th className={styles.numeric}>Kept / skipped</th>
                  <th className={styles.numeric}>Kept mean</th>
                  <th className={styles.numeric}>Skipped mean</th>
                  <th className={styles.numeric}>Contrast</th>
                  <th className={styles.numeric}>z</th>
                  <th className={styles.numeric}>Paired difference</th>
                  <th>Hold-out</th><th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {byStrength(cells).map((cell) => (
                  <tr key={`${cell.variable}-${cell.polarity}-${cell.horizon_minutes}`} className={cell.tested ? undefined : styles.untested}>
                    <td title={rule(cell)}>{cell.label}</td>
                    <td>{polarity(cell.polarity)}</td>
                    <td>{horizon(cell.horizon_minutes)}</td>
                    <td className={styles.numeric}>{count(cell.context_available)} / {count(cell.eligible)}</td>
                    <td className={styles.numeric}>{count(cell.retained)} / {count(cell.abstained)}</td>
                    <td className={styles.numeric}>{bps(cell.retained_mean_net_pct)}</td>
                    <td className={styles.numeric}>{bps(cell.abstained_mean_net_pct)}</td>
                    <td className={styles.numeric}>{bps(cell.contrast_pct)}</td>
                    <td className={styles.numeric}>{ratio(cell.z)}</td>
                    <td className={styles.numeric}>{bps(cell.paired_mean_difference_pct)}</td>
                    <td>{heldOut(cell)}</td>
                    <td>{verdict(cell)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p>
            Means are net of the stated round trip and are per call, not per account. The contrast is the tested quantity:
            kept calls minus skipped ones. The paired difference divides both by the same original count, so it rises
            whenever a filter simply takes fewer trades on a book that loses money after costs — that is arithmetic, not
            selection.
          </p>

          <details className={styles.details}>
            <summary>Population, coverage and the declared rule</summary>
            <p>
              {data.population_source?.why} Window: {data.population_source?.window_days} days ·{' '}
              {count(data.population_source?.opportunities)} calls with reconstructed evidence ·{' '}
              {data.population?.symbols?.length ?? 0} markets.
            </p>
            <p>
              Readings unavailable: no recorded book for {count(data.population_source?.coverage.no_recorded_book)} calls;
              no open-interest pair for {count(data.population_source?.coverage.no_open_interest_pair)}; no liquidation
              received for {count(data.population_source?.coverage.no_liquidation_received)}; no timeframe measurement for{' '}
              {count(data.population_source?.coverage.no_timeframe_measurement)} (none is stored for a past call, so that
              reading can only come from a live entry).
            </p>
            <p>{data.family?.rule}</p>
            <p>
              A cell is called measured only with at least {count(data.minimum_independent_windows)} non-overlapping
              windows on each side, symbols pooled; that is an operational floor, not a power calculation. Errors come from
              resampling whole time blocks one horizon long.
            </p>
            <p>
              Managed paper positions: {count(data.managed_paper?.positions)}. {data.managed_paper?.note}
            </p>
            <p>Costs: {data.costs?.source}.</p>
            <p>Declared family {data.family?.version} · {data.family?.sha256?.slice(0, 12)}…</p>
            <p className={styles.note}>{data.note}</p>
          </details>
        </>
      )}
    </section>
  )
}
