import { useRetentionPolicy } from '../../api/hooks/useOperatorSettings'
import { ReadingStamp } from '../ReadingStamp'
import { retentionLine } from './settingsText'
import styles from './SettingsPanels.module.css'

/** How long each kind of record is kept, as declared by the code that deletes it. */
export function RetentionPolicy() {
  const policy = useRetentionPolicy()
  const data = policy.data

  return (
    <section className="panel" aria-labelledby="retention-title">
      <div className="panel-heading">
        <div>
          <h3 id="retention-title">Retention</h3>
          <p>How far back each record goes before it is deleted.</p>
        </div>
        <ReadingStamp at={policy.dataUpdatedAt || null} onRefresh={() => void policy.refetch()} refreshing={policy.isFetching} />
      </div>
      <div className={styles.body}>
        {policy.isError && <p className={styles.warn}>Retention policy unavailable: {(policy.error as Error).message}</p>}
        {data && (
          <>
            <div className="table-scroll">
              <table className={styles.table}>
                <thead>
                  <tr><th scope="col">Record</th><th scope="col">Kept</th><th scope="col">Detail</th><th scope="col">Applied by</th></tr>
                </thead>
                <tbody>
                  {data.windows.map((window) => (
                    <tr key={window.table}>
                      <th scope="row">{window.what}<span className={styles.sub}>{window.table}</span></th>
                      <td className={styles.mono}>{retentionLine(window)}</td>
                      <td>
                        {window.detail}
                        {window.override && <span className={styles.sub}>override: {window.override}</span>}
                      </td>
                      <td>{window.run_by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className={styles.text}>{data.kept}</p>
            <p className={styles.note}>{data.note}</p>
          </>
        )}
      </div>
    </section>
  )
}
