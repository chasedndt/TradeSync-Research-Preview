import {
  BracketsCurly,
  ChartLineUp,
  Database,
  FlowArrow,
  GlobeHemisphereWest,
  HardDrives,
  Heartbeat,
  ListChecks,
  Prohibit,
  Robot,
  ShieldCheck,
  Stack,
} from '../icons'
import type { PipelineNode } from '../../api/types'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../../api/client'
import { readable, statusLabels, tone } from './pipelineStatus'

interface ConnectorStatus {
  status?: string
  detail?: string
  configured?: boolean
  projected?: { node_count: number; edge_count: number; ingested_at: string; build_info?: { errors?: number } }
}

const nodeIcons: Record<string, typeof Heartbeat> = {
  hyperliquid: GlobeHemisphereWest,
  market_data: ChartLineUp,
  redis: Stack,
  postgres: HardDrives,
  regime_engine: BracketsCurly,
  scorer_fusion: FlowArrow,
  performance_journal: ListChecks,
  tradingview_pine: ChartLineUp,
  strike_zone: ShieldCheck,
  agent_harness: Robot,
  chaseos: Database,
  execution: Prohibit,
}

export function PipelineNodeCard({ node }: { node: PipelineNode }) {
  const adapterPath = node.id === 'agent_harness' ? '/state/agents/harness/status' : node.id === 'chaseos' ? '/state/knowledge/graph/status' : null
  const adapter = useQuery({
    queryKey: ['pipeline-adapter-status', node.id],
    queryFn: () => apiGet<ConnectorStatus>(adapterPath!),
    enabled: adapterPath !== null,
    refetchInterval: 30_000,
    retry: 1,
  })
  const adapterLabel = adapterPath ? adapter.isError ? 'Status unavailable' : !adapter.data ? 'Checking adapter' :
    adapter.data.projected ? (adapter.data.configured ? 'Snapshot available' : 'Cached snapshot · sync off') :
    readable(adapter.data.status ?? 'unknown') : node.id === 'strike_zone' ? 'Pine submission source' : statusLabels[node.status]
  const Icon = nodeIcons[node.id] || Heartbeat
  const stateTone = tone(node.status)
  const research = node.research_run
  const researchTone = research?.fresh && research.validation_ok && research.missing_source_classes.length === 0
    ? 'good'
    : 'warn'

  return (
    <details className={`pipeline-node pipeline-node--${stateTone}`}>
      <summary>
        <span className={`pipeline-node-icon tone-${stateTone}`}><Icon size={23} weight="duotone" /></span>
        <span className="pipeline-node-heading">
          <span>{node.stage.replace(/_/g, ' ')} · Tier {node.tier}</span>
          <strong>{node.label}</strong>
          <small>{node.summary}</small>
        </span>
        <span className={`pipeline-state pipeline-state--${stateTone}`}>
          <span className="status-dot" />{adapterLabel}
          {/* A state without a duration is half a fact: "offline" reads the
              same whether it started ten seconds ago or yesterday. */}
          {node.state_age && node.state_age !== 'unknown' && (
            <small className="pipeline-state-age">for {node.state_age}</small>
          )}
          {node.flapping && (
            <small className="pipeline-state-flap" title={`${node.recent_transitions} changes in 15 minutes`}>
              unstable
            </small>
          )}
        </span>
      </summary>
      {research && (
        <section className="pipeline-research-receipt" aria-label="Latest Strike Zone evidence receipt">
          <div className="pipeline-research-heading">
            <div>
              <span className="pipeline-detail-label">Latest browser-research receipt</span>
              <strong>{research.run_slug}</strong>
              <small>
                {research.source_updated_at ? `Updated ${new Date(research.source_updated_at).toLocaleString()}` : 'Source timestamp unavailable'}
                {' · '}{research.fresh ? 'inside freshness window' : 'stale'}
              </small>
            </div>
            <span className={`pipeline-state pipeline-state--${researchTone}`}>
              <span className="status-dot" />{readable(research.status)}
            </span>
          </div>
          <div className="pipeline-research-metrics">
            <div><span>Evidence</span><strong>{research.evidence_item_count}</strong><small>bound items</small></div>
            <div><span>Charts</span><strong>{research.charts_captured}/{research.charts_expected}</strong><small>{research.assets.join(' · ') || 'assets unavailable'}</small></div>
            <div><span>Sources</span><strong>{research.required_source_classes.length - research.missing_source_classes.length}/{research.required_source_classes.length}</strong><small>required classes available</small></div>
            <div><span>Strict validation</span><strong className={`tone-${research.validation_ok ? 'good' : 'warn'}`}>{research.validation_ok ? 'PASS' : 'BLOCKED'}</strong><small>separate from evidence readiness</small></div>
          </div>
          <div className="pipeline-research-sources" aria-label="Evidence source counts">
            {Object.entries(research.source_counts).map(([source, count]) => (
              <span key={source}><b>{readable(source)}</b>{count}</span>
            ))}
          </div>
          {(research.missing_source_classes.length > 0 || research.validation_missing.length > 0) && (
            <div className="pipeline-research-gaps">
              {research.missing_source_classes.length > 0 && <p><b>Unavailable sources:</b> {research.missing_source_classes.map(readable).join(' · ')}</p>}
              {research.validation_missing.length > 0 && <p><b>Validation blockers:</b> {research.validation_missing.map(readable).join(' · ')}</p>}
            </div>
          )}
          <p className="pipeline-research-boundary">
            Research context only · operator approval required · external delivery {research.external_delivery_performed ? 'recorded' : 'not performed'} · execution authority false
          </p>
        </section>
      )}
      <div className="pipeline-node-detail">
        {adapterPath && <div>
          <span className="pipeline-detail-label">Adapter readback — separate from legacy health probe</span>
          <p>{adapter.isError ? 'Could not read adapter status; no availability is inferred.' : adapter.data?.detail ?? (adapter.data?.configured ? 'Adapter configured; this alone does not prove current delivery or task permission.' : 'Automatic connector configuration is absent. Existing cached data may still be readable.')}</p>
          {adapter.data?.projected && <p>{adapter.data.projected.node_count.toLocaleString()} nodes · {adapter.data.projected.edge_count.toLocaleString()} edges · imported {new Date(adapter.data.projected.ingested_at).toLocaleString()} · {adapter.data.projected.build_info?.errors ?? 'unknown'} extraction errors. Snapshot age is not live synchronization.</p>}
          {node.id === 'agent_harness' && <p>Reachability does not authorize jobs. Explanations and proposals only; scoring, approvals, execution and Discord publishing are separate boundaries.</p>}
        </div>}
        {node.id === 'strike_zone' && <p>Strike Zone Pine scripts execute on TradingView, not as a local health-check service. Local source files, authenticated webhook ingress, and the last accepted receipt must be verified separately. This label does not confirm delivery.</p>}
        <div>
          <span className="pipeline-detail-label">Verified evidence</span>
          <ul>{node.evidence.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <div>
          <span className="pipeline-detail-label">Missing or gated</span>
          {node.missing.length
            ? <ul>{node.missing.map((item) => <li key={item}>{item}</li>)}</ul>
            : <p>Nothing currently reported missing.</p>}
        </div>
        <div className="pipeline-recovery-callout">
          <span className="pipeline-detail-label">Impact</span>
          <p>{node.impact}</p>
          <span className="pipeline-detail-label">Next action · {readable(node.recovery.kind)}</span>
          <strong>{node.recovery.label}</strong>
          <small>Target: {node.recovery.target}</small>
          {node.recovery.command && <code>{node.recovery.command}</code>}
        </div>
      </div>
    </details>
  )
}
