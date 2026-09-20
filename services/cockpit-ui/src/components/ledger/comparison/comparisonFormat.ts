/** Reading the entry-evidence comparison: units, plain words for each verdict, and the order cells are shown in. */

export type Cell = {
  variable: string
  label: string
  polarity: string
  sign: number
  threshold: number
  horizon_minutes: number
  eligible: number
  context_available: number
  retained: number
  abstained: number
  independent_pooled: number
  baseline_mean_net_pct: number | null
  filter_mean_net_pct: number | null
  paired_mean_difference_pct: number | null
  retained_mean_net_pct: number | null
  abstained_mean_net_pct: number | null
  contrast_pct: number | null
  standard_error: number | null
  z: number | null
  p_positive: number | null
  detectable: boolean
  holdout_contrast_pct: number | null
  holdout_measured: number
  sample_state: string
  tested: boolean
  selects: boolean
  economic: boolean | null
  held_out: boolean | null
  notes: string[]
}

const finite = (v: number | null | undefined): v is number => v != null && Number.isFinite(v)

/** A percentage return as basis points, the unit the paper panels already use. 1% = 100 bps. */
export const bps = (percent: number | null | undefined, digits = 1): string =>
  finite(percent) ? `${(percent * 100).toFixed(digits)} bps` : '—'

export const count = (v: number | null | undefined): string => (finite(v) ? v.toLocaleString() : '—')

export const ratio = (v: number | null | undefined, digits = 2): string => (finite(v) ? v.toFixed(digits) : '—')

/** A p-value small enough to matter here never needs more than three decimals. */
export const chance = (v: number | null | undefined): string =>
  finite(v) ? (v < 0.001 ? '<0.001' : v.toFixed(3)) : '—'

export const horizon = (minutes: number): string => (minutes % 60 === 0 ? `${minutes / 60} h` : `${minutes} min`)

export const polarity = (name: string): string => (name === 'inverted' ? 'inverted' : 'as read')

/** The rule this cell applied, in words: "kept when book imbalance is at least 0.20". */
export const rule = (cell: Pick<Cell, 'label' | 'sign' | 'threshold'>): string =>
  `kept when ${cell.label.toLowerCase()}${cell.sign < 0 ? ', inverted,' : ''} is at least ${cell.threshold.toFixed(2)}`

const STATES: Record<string, string> = {
  no_context: 'no reading in this population',
  one_sided: 'every call fell on one side of the threshold',
  too_few_independent_windows: 'too few independent windows',
  measured: 'measured',
}

export const sampleState = (state: string): string => STATES[state] ?? state.replace(/_/g, ' ')

/**
 * What a cell found, in one phrase. A cell that was never tested says so rather
 * than reading as a negative result, and selection is kept apart from making money.
 */
export const verdict = (cell: Pick<Cell, 'sample_state' | 'tested' | 'selects' | 'economic'>): string => {
  if (!cell.tested) return `not tested · ${sampleState(cell.sample_state)}`
  if (!cell.selects) return 'no selection at the family bar'
  return cell.economic ? 'selects, and positive after costs' : 'selects, still negative after costs'
}

export const heldOut = (cell: Pick<Cell, 'held_out' | 'holdout_measured'>): string => {
  if (cell.held_out == null) return '—'
  return `${cell.held_out ? 'held' : 'did not hold'} on ${cell.holdout_measured}`
}

/** Strongest first, so a reader sees the best the family managed before the rest. */
export const byStrength = (cells: Cell[]): Cell[] =>
  [...cells].sort((a, b) => {
    if (a.tested !== b.tested) return a.tested ? -1 : 1
    return (b.z ?? Number.NEGATIVE_INFINITY) - (a.z ?? Number.NEGATIVE_INFINITY)
  })
