import type { ReactNode } from 'react'
import { SOURCE_STANDING, type SourceKind } from './liquidationSources'
import styles from './Liquidations.module.css'

const EDGE: Record<SourceKind, string> = {
  observed_events: styles.sectionObserved,
  venue_mechanics: styles.sectionVenue,
  inferred_pressure: styles.sectionInferred,
  legacy_proxy: styles.sectionProxy,
}

/**
 * One liquidation source, with what it is and whether a side may be attached to
 * it stated before any figure. The four sources are told apart here rather than
 * by the reader's inference, which is the whole point of separating them.
 */
export function SourceSection({ kind, children }: { kind: SourceKind; children: ReactNode }) {
  const standing = SOURCE_STANDING[kind]
  return (
    <section className={`${styles.section} ${EDGE[kind]}`} aria-label={standing.title}>
      <div className={styles.sectionHead}>
        <h4 className={styles.sectionTitle}>{standing.title}</h4>
        <span className={styles.standing}>{standing.authority.split('_').join(' ')}</span>
      </div>
      <p className={styles.basis}>{standing.basis}</p>
      <p className={`${styles.direction} ${standing.directionSupported ? styles.directionShown : styles.directionWithheld}`}>
        {standing.directionNote}
      </p>
      {children}
    </section>
  )
}
