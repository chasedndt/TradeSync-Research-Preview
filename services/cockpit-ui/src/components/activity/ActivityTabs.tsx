import { TABS, type TabId } from './activityFormat'
import styles from './ActivityTabs.module.css'

interface ActivityTabsProps {
  active: TabId
  /** The rows each tab's current reading holds; null when there is no current reading to count. */
  counts: Record<TabId, string | null>
  onSelect: (tab: TabId) => void
}

/** One tab per record: decisions, approvals, orders, alerts and outcomes. */
export function ActivityTabs({ active, counts, onSelect }: ActivityTabsProps) {
  return (
    <div className={styles.tabs} role="tablist" aria-label="Activity and evidence records">
      {TABS.map((tab) => {
        const count = counts[tab.id]
        return (
          <button
            key={tab.id}
            id={`activity-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={active === tab.id}
            aria-controls="activity-panel"
            className={active === tab.id ? 'chip chip--active' : 'chip'}
            onClick={() => onSelect(tab.id)}
          >
            {tab.label}
            {count !== null && <span className={styles.count}>{count}</span>}
          </button>
        )
      })}
    </div>
  )
}
