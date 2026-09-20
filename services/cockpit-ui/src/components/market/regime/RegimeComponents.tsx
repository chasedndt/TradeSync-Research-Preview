import { Fragment } from 'react'
import type { RegimeComponent, RegimeSummary } from '../../../api/regimeSummaryTypes'
import { ageWords, componentTone, exactUtc, regimeWords, statusWords } from './regimeSummaryText'
import styles from './Regime.module.css'

/** Each required input: what it read, where it came from, when, and whether it counted. */
export function RegimeComponents({ summary }: { summary: RegimeSummary }) {
  return (
    <div className={styles.section}>
      <h4 className={styles.sectionTitle}>Evidence behind the regime</h4>
      <div className="table-scroll">
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Input</th>
              <th scope="col">Reading</th>
              <th scope="col">Standing</th>
              <th scope="col">Read at</th>
              <th scope="col">Age</th>
            </tr>
          </thead>
          <tbody>
            {summary.components.map((component) => (
              <ComponentRows key={component.input} component={component} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ComponentRows({ component }: { component: RegimeComponent }) {
  const tone = componentTone(component)
  return (
    <Fragment>
      <tr>
        <th scope="row">{component.label}</th>
        <td className={styles.regimeCell}>{regimeWords(component.regime)}</td>
        <td className={`tone-${tone}`}>{statusWords(component)}</td>
        <td className={styles.sourceCell}>{exactUtc(component.observed_at_ms)}</td>
        <td>{ageWords(component.age_ms)}</td>
      </tr>
      {(component.reason || component.source) && (
        <tr className={styles.reasonRow}>
          <td colSpan={5}>
            {component.reason ?? `Counted from ${component.source}.`}
            {component.detail ? ` ${component.detail}` : ''}
          </td>
        </tr>
      )}
    </Fragment>
  )
}
