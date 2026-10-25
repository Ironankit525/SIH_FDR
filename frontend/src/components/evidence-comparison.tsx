import type { Row } from '@/lib/api'
import { label, money } from '@/lib/utils'
import { Badge, Notice, Panel } from './common'

const fields = ['bank', 'number', 'depositor_name', 'amount', 'issue_date', 'maturity_date']
const present = (value: unknown) => value !== undefined && value !== null && value !== ''
const display = (field: string, value: any) => !present(value) ? 'Not recorded' : field === 'amount'
  ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(value))
  : String(value)

function agree(field: string, values: unknown[]) {
  const normalized = values.map(value => field === 'amount'
    ? Number(String(value).replaceAll(',', '')).toFixed(2)
    : String(value).trim().toLocaleLowerCase())
  return normalized.every(value => value === normalized[0])
}

export function EvidenceComparison({ deposit, canCorrect, onCorrect }: {
  deposit: Row; canCorrect: boolean;
  onCorrect: (field: string, value: string, extractionId: string) => void
}) {
  const instrument = deposit.instrument
  const receipt = [...deposit.documents].reverse().find((doc: Row) => doc.category === 'instrument' && doc.instrument_id === instrument.id)
  const extraction = receipt?.extraction
  const evidence = deposit.verifications.find((item: Row) => item.instrument_id === instrument.id && item.evidence)?.evidence
  const corrections: Record<string, Row> = {}
  receipt?.corrections?.forEach((correction: Row) => { corrections[correction.field] = correction })
  const isModel = extraction?.provider?.startsWith('vlm')

  return <>
    <Notice>Compare each source separately. Matching values and extraction confidence do not prove authenticity. An officer must review discrepancies and bank evidence.</Notice>
    {receipt && !extraction && <Notice>The latest receipt has no extraction result yet: {label(receipt.processing_status)}. {receipt.processing_error || 'Its original document is available in the Documents tab.'}</Notice>}
    <Panel title="Side-by-side evidence" subtitle={receipt ? `Receipt: ${receipt.filename}` : 'Upload an instrument receipt to compare its details.'}>
      {extraction && <div className="evidence-provenance">
        <strong>{isModel ? 'Model extraction' : 'Document extraction'}</strong>
        <span>{isModel ? [extraction.model_name, extraction.model_version].filter(Boolean).join(' · ') : label(extraction.method)}</span>
        <small>Original values are preserved when a correction is recorded.</small>
      </div>}
      {extraction?.warnings?.map((warning: string, index: number) => <Notice key={index}>{warning}</Notice>)}
      <div className="table-scroll"><table className="comparison-table">
        <thead><tr><th>Field</th><th>Institution submitted</th><th>Document extraction</th><th>{evidence?.simulated ? 'SIMULATED bank evidence' : 'Bank evidence'}</th><th>Comparison</th></tr></thead>
        <tbody>{fields.map(field => {
          const raw = extraction?.fields?.[field]
          const correction = corrections[field]
          const reviewed = correction ? correction.corrected_value : raw
          const bank = evidence?.confirmed_fields?.[field]
          const confidence = extraction?.confidences?.[field]
          const values = [instrument[field], reviewed, bank].filter(present)
          const different = values.length > 1 && !agree(field, values)
          const complete = values.length === 3
          return <tr key={field}>
            <th>{label(field)}</th>
            <td>{display(field, instrument[field])}</td>
            <td>
              <strong>{present(reviewed) ? display(field, reviewed) : 'Not extracted'}</strong>
              {correction ? <>
                <small className="cell-subtitle">Human correction · {correction.reason}</small>
                <small className="cell-subtitle">Original extraction: {display(field, raw)}</small>
              </> : extraction && <small className="cell-subtitle">{typeof confidence === 'number'
                ? `${Math.round(confidence * 100)}% ${isModel ? 'model' : 'parser'} confidence`
                : 'Confidence not provided'}</small>}
              {extraction && canCorrect && <button className="inline-action" onClick={() => onCorrect(field, present(reviewed) ? String(reviewed) : '', extraction.id)}>Record correction</button>}
            </td>
            <td>{present(bank) ? display(field, bank) : evidence && !evidence.simulated ? 'See attached confirmation' : 'Not confirmed'}
              {evidence && <small className="cell-subtitle">Finding: {label(evidence.finding)}{evidence.simulated ? ' · Simulated' : ''}</small>}
            </td>
            <td><Badge value={different ? 'warning' : complete ? 'completed' : 'pending'}>{different ? 'Values differ' : complete ? 'Values agree' : 'Incomplete evidence'}</Badge></td>
          </tr>
        })}</tbody>
      </table></div>
      <div className="padded"><strong>Configured deposit requirement: </strong>{deposit.required_amount == null ? 'Manual review required' : money(deposit.required_amount)}
        <small className="cell-subtitle">{deposit.requirement_snapshot.illustrative ? 'Illustrative rule; officer review is required.' : deposit.requirement_snapshot.source_reference}</small>
      </div>
      {extraction && <details className="padded"><summary>View original extracted text and correction history</summary>
        <pre className="extracted-text">{extraction.original_text || 'The extraction service did not return a full text transcript.'}</pre>
        {receipt.corrections?.map((correction: Row) => <p key={correction.id}><strong>{label(correction.field)}:</strong> {correction.original_value || '(not extracted)'} → {correction.corrected_value} · {correction.reason}</p>)}
      </details>}
    </Panel>
  </>
}
