import type { BriefConfig, OpportunityBrief } from '../../../api/opportunityBriefTypes'
import { exactUtc } from '../../market/readingTime'
import { priceWords } from './briefText'
import styles from './Brief.module.css'

const configLine = (config: BriefConfig): string =>
  config.version ? `${config.id ?? '—'} ${config.version}` : 'not stored'

/**
 * Where the opportunity came from and what it can be checked against: the signal
 * that produced it, the scorer and schema, the evidence digest, the rulebook and
 * catalog it was scored under, the entry evidence fingerprint, and the opening
 * price the outcome job measured from. Digests are shown in full so they can be
 * compared with the stored rows.
 */
export function BriefProvenance({ brief }: { brief: OpportunityBrief }) {
  const p = brief.provenance

  return (
    <section className="panel" aria-labelledby="brief-provenance-title">
      <div className="panel-heading">
        <div>
          <h3 id="brief-provenance-title">Provenance</h3>
          <p>{brief.note}</p>
        </div>
      </div>
      <dl className={`${styles.provenance} ${styles.body}`}>
        <div><dt>Signal</dt><dd className={styles.digest}>{p.signal_id ?? 'not stored'}</dd></div>
        <div><dt>Scorer and decision schema</dt><dd>{p.scorer ?? 'not stored'} · {p.decision_schema ?? 'recorded before the paper signal schema'}</dd></div>
        <div><dt>Evaluated at</dt><dd>{exactUtc(p.evaluated_at_ms)}</dd></div>
        <div><dt>Evidence digest</dt><dd className={styles.digest}>{p.evidence_digest ?? 'not stored'}</dd></div>
        <div>
          <dt>Rulebook</dt>
          <dd>{configLine(p.rulebook)}</dd>
          {p.rulebook.digest && <dd className={styles.digest}>{p.rulebook.digest}</dd>}
        </div>
        <div>
          <dt>Feature catalog</dt>
          <dd>{configLine(p.catalog)}</dd>
          {p.catalog.digest && <dd className={styles.digest}>{p.catalog.digest}</dd>}
        </div>
        <div>
          <dt>Entry evidence fingerprint</dt>
          <dd className={styles.digest}>{p.entry_evidence_sha256 ?? 'no paper position, so no entry evidence was frozen'}</dd>
        </div>
        <div>
          <dt>Entry reference price</dt>
          <dd>{p.entry_reference_price == null ? 'not measured yet' : priceWords(p.entry_reference_price)}</dd>
          <dd className={styles.note}>{p.entry_reference_basis}</dd>
        </div>
        <div><dt>Authority</dt><dd>{brief.authority.split('_').join(' ')} · no approval, wallet or execution authority</dd></div>
      </dl>
    </section>
  )
}
