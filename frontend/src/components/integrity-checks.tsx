import { AlertTriangle, CheckCircle2, MinusCircle } from 'lucide-react'
import type { Row } from '@/lib/api'
import { dateLabel, label, money } from '@/lib/utils'

type Outcome = 'passed' | 'finding' | 'not_applicable'
interface Check { name: string; outcome: Outcome; detail: string; task?: Row }

const OUTCOME = {
  passed: { text: 'Passed', Icon: CheckCircle2 },
  finding: { text: 'Finding', Icon: AlertTriangle },
  not_applicable: { text: 'Not applicable', Icon: MinusCircle },
}

const fieldList = (keys: string[] = []) => keys.map(k => label(k).toLowerCase()).join(', ')

// PDF dates look like D:20260101103000+05'30'.
function pdfDate(value?: string) {
  const m = /^D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?/.exec(value || '')
  return m ? `${dateLabel(`${m[1]}-${m[2]}-${m[3]}`)}${m[4] ? `, ${m[4]}:${m[5] ?? '00'}` : ''}` : null
}

function fromSignals(report: Row, prefix: string) {
  return (report.signals || []).filter((s: Row) => s.code.startsWith(prefix))
}

function fileChecks(doc: Row): Check[] {
  const r = doc.forensics; const meta = r.metadata || {}; const structure = r.structure
  const check = (name: string, prefix: string, passedDetail: string, applicable = true): Check => {
    const found = fromSignals(r, prefix)
    if (found.length) return { name, outcome: 'finding', detail: found.map((s: Row) => s.detail).join(' ') }
    return { name, outcome: applicable ? 'passed' : 'not_applicable', detail: passedDetail }
  }
  if (doc.content_type !== 'application/pdf') {
    return [check('Editing software in image metadata', 'editing_software', meta.software ? `Software recorded: ${meta.software}` : 'No software recorded in the image.')]
  }
  const created = pdfDate(meta.creationDate), modified = pdfDate(meta.modDate)
  const crosscheck: Record<string, [Outcome, string]> = {
    completed: ['passed', `The visible page was read by OCR and matched the hidden text for: ${fieldList(r.compared_fields) || 'no comparable fields found'}.`],
    not_applicable: ['not_applicable', 'Scanned page with no hidden text layer; its text was read by OCR in the first place.'],
    skipped: ['not_applicable', 'Skipped for this record (seeded demonstration document).'],
    unavailable: ['not_applicable', 'Could not run: OCR was unavailable when the document was processed.'],
    not_run: ['not_applicable', 'Not run for this document.'],
  }
  const [ocrOutcome, ocrDetail] = crosscheck[r.ocr_crosscheck] || crosscheck.not_run
  const textLayer = structure?.text_layer !== false
  return [
    check('Editing software in metadata', 'editing_software', `Producer: ${meta.producer || 'not recorded'} · Creator: ${meta.creator || 'not recorded'}.`),
    check('Modified after creation', 'modified_after_creation', created && modified ? `Created ${created} · last modified ${modified}.` : 'No creation or modification dates recorded.', !!(created && modified)),
    check('Saved again after creation', 'incremental_update', !structure ? 'Not recorded for this document.'
      : structure.saves <= 1 ? 'Saved once: the file holds only its original version.' : `${structure.saves} sections, expected for a web-optimised (linearised) file.`, !!structure),
    check('Conflicting values in the text', 'conflicting_values_', textLayer ? `One value each for: ${fieldList(r.text_fields) || 'no key fields found in the text'}.` : 'No hidden text layer to examine.', textLayer),
    ...(fromSignals(r, 'text_layer_mismatch_').length ? [check('Visible page matches hidden text', 'text_layer_mismatch_', '')]
      : [{ name: 'Visible page matches hidden text', outcome: ocrOutcome, detail: ocrDetail }]),
  ]
}

// Checks made during review rather than on the file itself; each finding is a review task.
function reviewChecks(doc: Row, tasks: Row[]): Check[] {
  const fields = doc.extraction?.fields || {}
  const task = (code: string) => tasks.find(t => t.code === code)
  const fromTask = (name: string, code: string, passed: string, applicable = true): Check => {
    const found = task(code)
    if (found) return { name, outcome: 'finding', detail: found.description, task: found }
    return { name, outcome: applicable ? 'passed' : 'not_applicable', detail: passed }
  }
  const mismatches = tasks.filter(t => t.code.startsWith('mismatch_') && t.code.endsWith(`:${doc.id}`))
  const declaration: Check = mismatches.length
    ? { name: "Matches the institution's declaration", outcome: 'finding', detail: mismatches.map(t => t.description).join(' '), task: mismatches[0] }
    : { name: "Matches the institution's declaration", outcome: doc.extraction ? 'passed' : 'not_applicable',
        detail: doc.extraction ? 'Every key field read from the document matches what the institution declared.' : 'Nothing has been read from the document yet.' }
  return [
    declaration,
    // State the figures checked: they come from the document's text, which may differ from what the page shows.
    fromTask('Receipt arithmetic', `maturity_value_inconsistent:${doc.id}`,
      fields.maturity_value ? `Read from the document: principal ${money(fields.amount)}, maturity value ${money(fields.maturity_value)}${fields.rate ? ` at ${fields.rate}%` : ''}. These fit together for its term.`
        : 'The receipt does not print a maturity value, so there is nothing to check.', !!(fields.maturity_value && fields.amount)),
    fromTask('Same file on another case', `reused_document:${doc.sha256}`, 'This exact file has not been submitted on any other case.'),
    fromTask('Same text on another case', `reused_text:${doc.id}`, 'No earlier case holds a document with identical text.'),
    fromTask('Reference number on another case', `extracted_number_elsewhere:${doc.id}`,
      fields.number ? `Reference ${fields.number} is not recorded on any earlier case.` : 'No reference number was read from the document.', !!fields.number),
  ]
}

export function IntegrityChecks({ doc, tasks }: { doc: Row; tasks: Row[] }) {
  const report = doc.forensics
  if (doc.category !== 'instrument' || report === undefined) return null
  if (['queued', 'processing'].includes(doc.processing_status)) return <p className="integrity-note">Integrity checks run once extraction finishes.</p>
  if (!report || !report.version) return <p className="integrity-note">No integrity report is recorded for this document; it was uploaded before these checks existed.</p>
  if (report.error) return <p className="integrity-note">{report.error}</p>
  const checks = [...fileChecks(doc), ...reviewChecks(doc, tasks)]
  const findings = checks.filter(c => c.outcome === 'finding').length
  const ran = checks.filter(c => c.outcome !== 'not_applicable').length
  return <details className="integrity-checks" open={findings > 0}>
    <summary>Integrity checks · {ran} run · {findings ? `${findings} finding${findings > 1 ? 's' : ''}` : 'no findings'}</summary>
    <ul>{checks.map(c => { const { text, Icon } = OUTCOME[c.outcome]; return <li key={c.name} className={`check-row ${c.outcome}`}>
      <span className="check-outcome"><Icon size={14} aria-hidden/>{text}</span>
      <div><strong>{c.name}</strong><p>{c.detail}</p>{c.task && <small>Review task {label(c.task.status).toLowerCase()} · {label(c.task.severity).toLowerCase()} severity</small>}</div>
    </li> })}</ul>
    <p className="integrity-note">Checks look for signs of alteration and reuse. Passing them does not prove a document is genuine; only the issuing bank can confirm that.</p>
  </details>
}
