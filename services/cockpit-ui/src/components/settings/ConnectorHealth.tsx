import { useIntegrationPipeline } from '../../api/hooks'
import { FeedHeartbeats } from '../pipeline/FeedHeartbeats'
import { ReadingStamp } from '../ReadingStamp'
import styles from './SettingsPanels.module.css'

/**
 * Connector health: every feed's heartbeat, shown by the same panel the
 * integration pipeline page uses rather than a second copy of it.
 */
export function ConnectorHealth() {
  const pipeline = useIntegrationPipeline()
  const feeds = pipeline.data?.feeds

  return (
    <div className={styles.stack}>
      <div className={styles.toolbar}>
        <h4>Connector health</h4>
        <ReadingStamp
          at={feeds ? Date.parse(feeds.generated_at) : null}
          onRefresh={() => void pipeline.refetch()}
          refreshing={pipeline.isFetching}
        />
      </div>
      <FeedHeartbeats feeds={feeds} />
    </div>
  )
}
