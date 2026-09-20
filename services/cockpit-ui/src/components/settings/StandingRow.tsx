import type { Standing } from './settingsText'
import styles from './SettingsPanels.module.css'

/** One standing in a definition list: its name, its label in the standing's tone, and the detail behind it. */
export function StandingRow({ name, standing }: { name: string; standing: Standing }) {
  return (
    <div>
      <dt>{name}</dt>
      <dd className={`${styles.value} tone-${standing.tone}`}>{standing.label}</dd>
      <dd>{standing.detail}</dd>
    </div>
  )
}
