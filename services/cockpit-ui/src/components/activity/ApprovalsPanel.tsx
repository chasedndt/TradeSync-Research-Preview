import type { ApprovalRow } from '../../api/activityTypes'
import { AuditSectionPanel, type AuditPanelProps } from './AuditSectionPanel'
import { Carried, ShortCode, Stamp } from './cells'
import { EvidenceTable, type Column } from './EvidenceTable'
import { approvalState, distinct } from './rowFormat'

const DIGEST = 12

const COLUMNS: Column<ApprovalRow>[] = [
  { id: 'bound', header: 'Bound', cell: (row) => <Stamp value={row.created_at} /> },
  { id: 'approved', header: 'Approved', cell: (row) => <Stamp value={row.approved_at} /> },
  { id: 'state', header: 'State', cell: (row) => approvalState(row.consumed_at) },
  { id: 'consumed', header: 'Consumed', cell: (row) => <Stamp value={row.consumed_at} /> },
  { id: 'consumed-by', header: 'Consumed by', cell: (row) => row.consumed_by ?? '—' },
  { id: 'candidate', header: 'Candidate', cell: (row) => <ShortCode value={row.candidate_id} length={DIGEST} /> },
  { id: 'candidate-hash', header: 'Candidate hash', cell: (row) => <ShortCode value={row.candidate_hash} length={DIGEST} /> },
  { id: 'approval-digest', header: 'Approval digest', cell: (row) => <ShortCode value={row.approval_digest} length={DIGEST} /> },
  { id: 'chaseos-decision', header: 'ChaseOS decision', cell: (row) => <ShortCode value={row.approval_decision_id} /> },
  { id: 'approval', header: 'Approval', cell: (row) => <ShortCode value={row.approval_id} /> },
  { id: 'envelope', header: 'Envelope', cell: (row) => <ShortCode value={row.envelope_id} /> },
]

/** ChaseOS approvals bound to paper candidates, with the digests that prove what was approved. */
export function ApprovalsPanel(props: AuditPanelProps) {
  return (
    <AuditSectionPanel
      {...props}
      tab="approvals"
      description="Each row binds one ChaseOS approval to one paper candidate, with the approval digest and the hash of the candidate it was granted for. A row is written only once an approval is bound, so every row is approved; what differs is whether a paper evaluation has consumed it. An approval authorises one paper evaluation, never an order."
    >
      {(section) => (
        <>
          <Carried items={[{ label: 'States in these rows', values: distinct(section.rows.map((row) => approvalState(row.consumed_at))) }]} />
          <EvidenceTable label="Approvals" columns={COLUMNS} rows={section.rows} rowKey={(row) => row.envelope_id} />
        </>
      )}
    </AuditSectionPanel>
  )
}
