import { getApiBaseUrl } from '../../api/credentials'
import { useHealth, useIntegrationPipeline } from '../../api/hooks'
import { exactUtc } from '../market/readingTime'
import { statusLabels, tone } from '../pipeline/pipelineStatus'
import { ReadingStamp } from '../ReadingStamp'
import { StateApiAddress } from './StateApiAddress'
import styles from './SettingsPanels.module.css'

/**
 * Where the Cockpit reads from and how each connection stands: the state API
 * address in use and its database health, then every stage of the integration
 * pipeline with the status its live probe measured. Feed heartbeats follow in
 * their own panel.
 */
export function DataConnections() {
  const health = useHealth()
  const pipeline = useIntegrationPipeline()
  const data = pipeline.data
  const readAt = data ? Date.parse(data.generated_at) : pipeline.dataUpdatedAt || null

  return (
    <section className="panel" aria-labelledby="data-connections-title">
      <div className="panel-heading">
        <div>
          <h3 id="data-connections-title">Data connections</h3>
          <p>
            {data
              ? `Tier A ${data.tier_a.status}: ${data.tier_a.ready_count} of ${data.tier_a.total_count} required stages ready`
              : pipeline.isError ? 'The integration pipeline could not be read' : 'Reading the integration pipeline…'}
          </p>
        </div>
        <ReadingStamp
          at={readAt}
          onRefresh={() => { void pipeline.refetch(); void health.refetch() }}
          refreshing={pipeline.isFetching || health.isFetching}
        />
      </div>
      <div className={styles.body}>
        <dl className={styles.standings}>
          <div><dt>State API address</dt><dd className={styles.value}>{getApiBaseUrl()}</dd></div>
          <div>
            <dt>State API and database</dt>
            <dd className={`${styles.value} tone-${health.data?.postgres ? 'good' : 'bad'}`}>
              {health.data
                ? `${health.data.status}, database ${health.data.postgres ? 'answering' : 'not answering'}`
                : health.isError ? 'not answering' : 'checking…'}
            </dd>
            {health.data && <dd>Database read in {health.data.latency_ms.toFixed(0)} ms.</dd>}
          </div>
        </dl>

        {data && (
          <div className="table-scroll">
            <table className={styles.table}>
              <thead>
                <tr><th scope="col">Connection</th><th scope="col">Status</th><th scope="col">In this state since</th><th scope="col">What it reports</th></tr>
              </thead>
              <tbody>
                {data.nodes.map((node) => (
                  <tr key={node.id}>
                    <th scope="row">
                      {node.label}
                      <span className={styles.sub}>{node.required_for_tier_a ? 'required for Tier A' : 'optional'}</span>
                    </th>
                    <td className={`tone-${tone(node.status)}`}>{statusLabels[node.status] ?? node.status}</td>
                    <td className={styles.mono}>
                      {node.state_since_epoch_s ? exactUtc(node.state_since_epoch_s * 1000) : 'not recorded'}
                    </td>
                    <td>{node.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <p className={styles.note}>{data.tier_a.principle}</p>}
        <StateApiAddress />
      </div>
    </section>
  )
}
