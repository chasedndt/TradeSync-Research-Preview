import type { OpportunityBrief } from '../../../api/opportunityBriefTypes'
import { exactUtc } from '../../market/readingTime'
import styles from './Brief.module.css'

const figure = (value: number | null | undefined, digits = 3): string =>
  value == null || !Number.isFinite(value) ? '—' : value.toFixed(digits)

/**
 * The readings that carried the decision, as they were stored with it: each
 * contributing feature with its block, score, quality, provenance and read time,
 * the blocks that had no evidence, and the paper risk caps that applied.
 */
export function BriefEvidence({ brief }: { brief: OpportunityBrief }) {
  const { evidence } = brief
  const features = evidence.contributing_features

  return (
    <section className="panel" aria-labelledby="brief-evidence-title">
      <div className="panel-heading">
        <div>
          <h3 id="brief-evidence-title">Evidence stored with the decision</h3>
          <p>
            {features.length === 0
              ? 'No contributing feature was stored with this opportunity.'
              : `${features.length} contributing feature${features.length === 1 ? '' : 's'}, as scored at the time`}
          </p>
        </div>
      </div>
      <div className={styles.body}>
        {features.length > 0 && (
          <div className="table-scroll">
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Feature</th>
                  <th scope="col">Block</th>
                  <th scope="col">Score</th>
                  <th scope="col">Quality</th>
                  <th scope="col">Provenance</th>
                  <th scope="col">Read at</th>
                </tr>
              </thead>
              <tbody>
                {features.map((feature) => (
                  <tr key={feature.feature_id}>
                    <th scope="row" className={styles.mono}>{feature.feature_id}</th>
                    <td>{feature.block ?? '—'}</td>
                    <td className={styles.mono}>{figure(feature.score)}</td>
                    <td className={styles.mono}>{figure(feature.data_quality, 2)}</td>
                    <td>{feature.provenance ?? '—'}</td>
                    <td className={styles.mono}>{exactUtc(feature.observed_at_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {evidence.directional_contributors.length > 0 && (
          <div className={styles.block}>
            <h4 className={styles.blockTitle}>Readings allowed to set the side</h4>
            <ul className={styles.chips}>
              {evidence.directional_contributors.map((item) => (
                <li key={item.feature_id}>{item.feature_id} {figure(item.score)}</li>
              ))}
            </ul>
          </div>
        )}

        <div className={styles.block}>
          <h4 className={styles.blockTitle}>Blocks without evidence</h4>
          {evidence.missing_blocks.length > 0 ? (
            <ul className={styles.chips}>{evidence.missing_blocks.map((block) => <li key={block}>{block}</li>)}</ul>
          ) : (
            <p className={styles.note}>Every block had evidence, or none was recorded as missing.</p>
          )}
        </div>

        {evidence.risk_caps_applied.length > 0 && (
          <div className={styles.block}>
            <h4 className={styles.blockTitle}>Paper risk caps applied</h4>
            <ul className={styles.chips}>
              {evidence.risk_caps_applied.map((cap) => <li key={cap.flag}>{cap.flag} × {cap.cap}</li>)}
            </ul>
            <p className={styles.note}>Paper risk multiplier as stored: {figure(evidence.paper_risk_multiplier, 2)}.</p>
          </div>
        )}
      </div>
    </section>
  )
}
