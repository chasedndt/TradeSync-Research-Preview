import { Link } from 'react-router-dom'
import type { OutcomeRow } from '../../api/activityTypes'
import { codeLabel } from '../ledger/paperRisk/paperRiskFormat'
import { AuditSectionPanel, type AuditPanelProps } from './AuditSectionPanel'
import { Carried, OpportunityLink, ShortCode, Stamp, Toned } from './cells'
import { EvidenceTable, type Column } from './EvidenceTable'
import { distinct, horizonText, outcomeStatus, percentText, priceRangeText } from './rowFormat'

const COLUMNS: Column<OutcomeRow>[] = [
  { id: 'called', header: 'Called', cell: (row) => <Stamp value={row.opened_at} /> },
  { id: 'market', header: 'Market', cell: (row) => row.symbol },
  { id: 'side', header: 'Side', cell: (row) => codeLabel(row.direction) },
  { id: 'horizon', header: 'Horizon', cell: (row) => horizonText(row.horizon_minutes) },
  { id: 'status', header: 'Status', cell: (row) => <Toned {...outcomeStatus(row.status)} /> },
  { id: 'signed', header: 'Signed return', cell: (row) => percentText(row.signed_return_pct) },
  { id: 'move', header: 'Market move', cell: (row) => percentText(row.forward_return_pct) },
  { id: 'favourable', header: 'Max favourable', cell: (row) => percentText(row.max_favourable_pct) },
  { id: 'adverse', header: 'Max adverse', cell: (row) => percentText(row.max_adverse_pct) },
  { id: 'prices', header: 'Entry → exit', cell: (row) => priceRangeText(row.entry_price, row.exit_price) },
  { id: 'candles', header: 'Candles', cell: (row) => row.candles_used },
  { id: 'reason', header: 'Reason', cell: (row) => row.reason || '—', wrap: true },
  { id: 'measured', header: 'Measured', cell: (row) => <Stamp value={row.measured_at} /> },
  { id: 'digest', header: 'Evidence digest', cell: (row) => <ShortCode value={row.evidence_digest} length={12} /> },
  { id: 'opportunity', header: 'Opportunity', cell: (row) => <OpportunityLink id={row.opportunity_id} /> },
]

/** What the market did after each recorded paper call, per horizon, as state-api measured it. */
export function OutcomesPanel(props: AuditPanelProps) {
  return (
    <AuditSectionPanel
      {...props}
      tab="outcomes"
      description={
        <>
          What the market did after each recorded paper call, one row per horizon, as state-api measured it. Signed return is the
          move in the direction called; max favourable and max adverse are the furthest the price went each way. No position
          existed, so these rows carry no fees, funding or slippage: costed paper positions and thesis adherence are on
          the <Link to="/signal-ledger">Signal Ledger</Link>.
        </>
      }
    >
      {(section) => (
        <>
          <Carried items={[{ label: 'Statuses in these rows', values: distinct(section.rows.map((row) => outcomeStatus(row.status).text)) }]} />
          <EvidenceTable
            label="Outcomes"
            columns={COLUMNS}
            rows={section.rows}
            rowKey={(row) => `${row.opportunity_id}-${row.horizon_minutes}`}
          />
        </>
      )}
    </AuditSectionPanel>
  )
}
