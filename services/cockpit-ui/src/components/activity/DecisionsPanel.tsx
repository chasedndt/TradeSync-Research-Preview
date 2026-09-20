import { Link } from 'react-router-dom'
import type { DecisionRow } from '../../api/activityTypes'
import { AuditSectionPanel, type AuditPanelProps } from './AuditSectionPanel'
import { Carried, OpportunityLink, ShortCode, Stamp, Toned } from './cells'
import { EvidenceTable, type Column } from './EvidenceTable'
import { decisionReason, decisionVerdict, distinct, payloadNumber, payloadText, usdText } from './rowFormat'

const COLUMNS: Column<DecisionRow>[] = [
  { id: 'recorded', header: 'Recorded', cell: (row) => <Stamp value={row.created_at} /> },
  { id: 'market', header: 'Market', cell: (row) => payloadText(row.requested, 'symbol') ?? '—' },
  { id: 'action', header: 'Plan', cell: (row) => payloadText(row.requested, 'action') ?? '—' },
  { id: 'size', header: 'Size', cell: (row) => usdText(payloadNumber(row.requested, 'size_usd')) },
  { id: 'verdict', header: 'Verdict', cell: (row) => <Toned {...decisionVerdict(row.risk)} /> },
  { id: 'reason', header: 'Policy reason', cell: (row) => decisionReason(row.risk), wrap: true },
  { id: 'opportunity', header: 'Opportunity', cell: (row) => <OpportunityLink id={row.opportunity_id} /> },
  { id: 'decision', header: 'Decision', cell: (row) => <ShortCode value={row.id} /> },
]

/** Risk decisions as stored: the plan, the verdict and its policy reason. */
export function DecisionsPanel(props: AuditPanelProps) {
  return (
    <AuditSectionPanel
      {...props}
      tab="decisions"
      description={
        <>
          Each row is an execution plan with the risk verdict and policy reason stored beside it. Only a preview the risk check
          allows is stored: a blocked preview leaves no row, and while the execution gate is closed the check blocks every
          preview. Paper rehearsals keep their own journal, on <Link to="/execution">Execution readiness</Link>.
        </>
      }
    >
      {(section) => (
        <>
          <Carried
            items={[
              { label: 'Verdicts in these rows', values: distinct(section.rows.map((row) => decisionVerdict(row.risk).text)) },
              { label: 'Reason codes', values: distinct(section.rows.map((row) => payloadText(row.risk, 'reason_code'))) },
            ]}
          />
          <EvidenceTable label="Decisions" columns={COLUMNS} rows={section.rows} rowKey={(row) => row.id} />
        </>
      )}
    </AuditSectionPanel>
  )
}
