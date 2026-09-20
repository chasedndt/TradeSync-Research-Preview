import { Link } from 'react-router-dom'
import { utcStamp } from './activityFormat'
import { shortId, type Labelled } from './rowFormat'
import styles from './cells.module.css'

/** Stateless cell renderers shared by the Activity & Evidence tables. */

const Dash = () => <span className="tone-dim">—</span>

/** A stored time as an exact UTC stamp. */
export function Stamp({ value }: { value: string | null | undefined }) {
  return value ? <time dateTime={value} className={styles.mono}>{utcStamp(value)}</time> : <Dash />
}

/** The start of an identifier or digest; the whole value is in its title, to be copied or compared. */
export function ShortCode({ value, length }: { value: string | null | undefined; length?: number }) {
  return value ? <code className={styles.code} title={value}>{shortId(value, length)}</code> : <Dash />
}

export function Toned({ text, tone }: Labelled) {
  return <span className={tone === 'plain' ? undefined : `tone-${tone}`}>{text}</span>
}

/** A recorded opportunity, opening its detail page. */
export function OpportunityLink({ id }: { id: string | null | undefined }) {
  return id ? <Link to={`/opportunities/${id}`} className={styles.code} title={id}>{shortId(id)}</Link> : <Dash />
}

/** The values a column actually carries in the rows shown, each once. Nothing when the rows carry none. */
export function Carried({ items }: { items: { label: string; values: string[] }[] }) {
  const shown = items.filter((item) => item.values.length > 0)
  if (shown.length === 0) return null
  return (
    <dl className={styles.carried}>
      {shown.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.values.join(' · ')}</dd>
        </div>
      ))}
    </dl>
  )
}
