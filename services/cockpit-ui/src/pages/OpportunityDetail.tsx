import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useEvidence, useExecute, useMarketSnapshot, usePreview } from '../api/hooks'
import { useOpportunityBrief } from '../api/hooks/useOpportunityBriefs'
import type { ExecutionResult, MarketSnapshotWithMicrostructure, PreviewResponse } from '../api/types'
import { EvidenceTrail, PreviewPanel } from '../components'
import { BriefEntryConditions } from '../components/opportunity/brief/BriefEntryConditions'
import { BriefEvidence } from '../components/opportunity/brief/BriefEvidence'
import { BriefHeader } from '../components/opportunity/brief/BriefHeader'
import { BriefPlan } from '../components/opportunity/brief/BriefPlan'
import { BriefProvenance } from '../components/opportunity/brief/BriefProvenance'
import { ExecuteResultCard } from '../components/opportunity/ExecuteResultCard'
import { ExecutionRiskBox } from '../components/opportunity/ExecutionRiskBox'
import { MarketContextCard } from '../components/opportunity/MarketContextCard'
import { OpportunityOutcomes } from '../components/opportunity/OpportunityOutcomes'
import { PreviewForm } from '../components/opportunity/PreviewForm'
import styles from './OpportunityDetail.module.css'

/**
 * One opportunity: its brief (side, regime fit, entry conditions, paper plan,
 * evidence, provenance and paper state, each read from stored records), what the
 * market did after it, the evidence trail, and the existing preview controls.
 * When the brief cannot be read, the stored record is still shown without it.
 */
export function OpportunityDetail() {
  const { id } = useParams<{ id: string }>()
  const brief = useOpportunityBrief(id)
  const { data: evidence, isLoading: evidenceLoading } = useEvidence(id)
  const previewMutation = usePreview()
  const executeMutation = useExecute()

  const symbol = brief.data?.symbol || evidence?.opportunity?.symbol || ''
  const { data: marketSnapshot } = useMarketSnapshot('hyperliquid', symbol)

  const [sizeUsd, setSizeUsd] = useState(1000)
  const [venue, setVenue] = useState('hyperliquid')
  const [previewResult, setPreviewResult] = useState<PreviewResponse | null>(null)
  const [executeResult, setExecuteResult] = useState<ExecutionResult | null>(null)

  const handlePreview = async () => {
    if (!id) return
    setExecuteResult(null)
    const result = await previewMutation.mutateAsync({ opportunity_id: id, size_usd: sizeUsd, venue })
    setPreviewResult(result)
  }

  const handleExecute = async (decisionId: string) => {
    const result = await executeMutation.mutateAsync({ decision_id: decisionId, confirm: true })
    setExecuteResult(result)
  }

  const data = brief.data
  const opportunity = evidence?.opportunity
  const back = <Link to="/opportunities" className={styles.back}>&larr; Back to Opportunities</Link>

  if (!data && !opportunity) {
    return (
      <div className={styles.page}>
        {back}
        {brief.isLoading || evidenceLoading
          ? <p className={styles.message}>Reading the stored opportunity…</p>
          : <p className={styles.error}>This opportunity could not be read{brief.error ? `: ${(brief.error as Error).message}` : ''}.</p>}
      </div>
    )
  }

  return (
    <div className={styles.page}>
      {back}
      {data ? (
        <BriefHeader brief={data} onRefresh={() => void brief.refetch()} refreshing={brief.isFetching} />
      ) : (
        <p className={brief.isLoading ? styles.message : styles.error}>
          {brief.isLoading
            ? 'Reading the brief…'
            : `The brief could not be read${brief.error ? `: ${(brief.error as Error).message}` : ''}. The stored record below is shown without it.`}
        </p>
      )}

      <div className={styles.columns}>
        <div className={styles.main}>
          {data && <BriefEntryConditions brief={data} />}
          {data && <BriefPlan plan={data.plan} />}
          {id && <OpportunityOutcomes opportunityId={id} />}
          {data && <BriefEvidence brief={data} />}
          {evidence && (
            <section>
              <h3 className={styles.sectionTitle}>Evidence Trail</h3>
              <EvidenceTrail evidence={evidence} />
            </section>
          )}
          <MarketContextCard marketSnapshot={marketSnapshot} symbol={symbol} />
          <ExecutionRiskBox
            marketSnapshot={marketSnapshot as MarketSnapshotWithMicrostructure}
            confluence={(evidence?.opportunity as any)?.confluence}
          />
        </div>

        <div className={styles.side}>
          {data && <BriefProvenance brief={data} />}
          {opportunity && (
            <section>
              <h3 className={styles.sectionTitle}>Execution Control</h3>
              {opportunity.status !== 'executed' && (
                <PreviewForm
                  sizeUsd={sizeUsd}
                  onSizeUsdChange={setSizeUsd}
                  venue={venue}
                  onVenueChange={setVenue}
                  onPreview={handlePreview}
                  isPending={previewMutation.isPending}
                />
              )}
              {previewResult && !executeResult && (
                <PreviewPanel preview={previewResult} onExecute={handleExecute} isExecuting={executeMutation.isPending} />
              )}
              {executeResult && (
                <ExecuteResultCard executeResult={executeResult} onDismiss={() => setExecuteResult(null)} />
              )}
              {opportunity.status === 'executed' && !executeResult && (
                <p className={styles.message}>Entry complete. Monitoring position in Portfolio.</p>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
