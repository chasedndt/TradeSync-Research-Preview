import type { OrderRow } from '../../api/activityTypes'
import { AuditSectionPanel, type AuditPanelProps } from './AuditSectionPanel'
import { Carried, ShortCode, Stamp, Toned } from './cells'
import { EvidenceTable, type Column } from './EvidenceTable'
import { distinct, orderError, orderMode, orderStatus, payloadNumber, payloadText, usdText } from './rowFormat'

const COLUMNS: Column<OrderRow>[] = [
  { id: 'recorded', header: 'Recorded', cell: (row) => <Stamp value={row.created_at} /> },
  { id: 'status', header: 'Status', cell: (row) => <Toned {...orderStatus(row.status)} /> },
  { id: 'mode', header: 'Mode', cell: (row) => orderMode(row.dry_run) },
  { id: 'market', header: 'Market', cell: (row) => payloadText(row.request, 'symbol') ?? '—' },
  { id: 'size', header: 'Size', cell: (row) => usdText(payloadNumber(row.request, 'size_usd')) },
  { id: 'error', header: 'Error', cell: (row) => orderError(row.response) ?? '—', wrap: true },
  { id: 'order', header: 'Order', cell: (row) => <ShortCode value={row.id} /> },
  { id: 'decision', header: 'Decision', cell: (row) => <ShortCode value={row.decision_id} /> },
  { id: 'txid', header: 'Transaction', cell: (row) => <ShortCode value={row.txid} length={12} /> },
]

/** Order records as stored: status exactly as the execution boundary returned it, and the paper flag. */
export function OrdersPanel(props: AuditPanelProps) {
  return (
    <AuditSectionPanel
      {...props}
      tab="orders"
      description="Each row is the order record kept for a stored decision: the status the execution boundary returned, stored as it came, and the mode flag stored with it. Paper means the order was not sent to a venue. The execution gate is checked again before an order is recorded, so while it is closed no order row is written."
    >
      {(section) => (
        <>
          <Carried
            items={[
              { label: 'Statuses in these rows', values: distinct(section.rows.map((row) => orderStatus(row.status).text)) },
              { label: 'Modes', values: distinct(section.rows.map((row) => (row.dry_run == null ? null : orderMode(row.dry_run)))) },
            ]}
          />
          <EvidenceTable label="Orders" columns={COLUMNS} rows={section.rows} rowKey={(row) => row.id} />
        </>
      )}
    </AuditSectionPanel>
  )
}
