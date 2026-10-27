import type { Row } from '@/lib/api'
import { label } from '@/lib/utils'
import { Badge, Notice } from './common'

export function ExtractionStatus({ doc }: { doc: Row }) {
  const status = doc.category === 'instrument' && doc.processing_status === 'completed' && doc.extraction?.evidence?.status
  if (status === 'conflict') return <Badge value="warning">Conflicting extraction</Badge>
  if (status === 'incomplete') return <Badge value="warning">Incomplete extraction</Badge>
  return <Badge value={doc.processing_status}/>
}

const sourceName = (value: string) => ({ pdf_text: 'PDF text', ocr: 'OCR', vlm_http: 'VLM', vlm_local: 'VLM' }[value] || label(value))

export function ExtractionEvidence({ evidence }: { evidence?: Row }) {
  if (!evidence?.status) return null
  return <div className="padded">
    {evidence.status !== 'complete' && <Notice tone="warning">
      <strong>{evidence.status === 'conflict' ? 'Extraction sources disagree. Manual review required.' : 'Extraction is incomplete. Manual review required.'}</strong>
      {evidence.reasons?.length > 0 && <p>{evidence.reasons.join('; ')}</p>}
      <p>Processing has finished. This does not establish that the receipt is genuine.</p>
    </Notice>}
    {evidence.conflicts?.map((conflict: Row) => <div key={conflict.field} className="padded">
      <strong>{label(conflict.field)} disagreement</strong>
      <ul>{conflict.observations.map((item: Row, index: number) => <li key={index}>{sourceName(item.source)}: {String(item.value)}</li>)}</ul>
      <small>Compare with the original receipt before recording a correction. Source values are preserved.</small>
    </div>)}
    <details>
      <summary>Extraction stages and original source values</summary>
      <ol>{evidence.stages?.map((stage: Row, index: number) => <li key={index}>
        {sourceName(stage.stage)}: {label(stage.outcome)}{stage.reasons?.length ? ` — ${stage.reasons.join('; ')}` : ''}
      </li>)}</ol>
      {evidence.sources?.map((source: Row, index: number) => <section key={index}>
        <h3>{sourceName(source.provider)}</h3>
        <dl className="detail-list">{Object.entries(source.fields || {}).map(([field, value]) => <div key={field}><dt>{label(field)}</dt><dd>{String(value)}</dd></div>)}</dl>
        {source.original_text && <details><summary>Original text from {sourceName(source.provider)}</summary><pre className="extracted-text">{source.original_text}</pre></details>}
      </section>)}
    </details>
  </div>
}
