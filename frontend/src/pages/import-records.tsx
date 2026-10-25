import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Download, FileUp, Upload } from 'lucide-react'
import { useUser } from '@/App'
import { api, type Row } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge, ErrorState, Notice, PageHeader, Panel } from '@/components/common'

const COLUMNS = ['institution_code', 'programme', 'level', 'bank', 'branch', 'number', 'depositor_name', 'amount', 'issue_date', 'maturity_date',
                 'instrument_type', 'validity_date', 'lien_details', 'regulatory_end_date', 'renewal_due_date']
const EXAMPLE = ['DEMO-INST-001', 'Engineering and Technology', 'undergraduate', 'State Bank of India', 'Main Branch', 'SBI-2024-000123',
                 'Meridian Institute of Technology', '3500000', '2024-04-01', '2029-03-31', 'FDR', '', 'Lien marked in favour of AICTE', '2028-03-31', '']

function downloadTemplate() {
  const quote = (v: string) => /[",\n]/.test(v) ? `"${v.replaceAll('"', '""')}"` : v
  const url = URL.createObjectURL(new Blob([`${COLUMNS.join(',')}\n${EXAMPLE.map(quote).join(',')}\n`], { type: 'text/csv' }))
  const link = document.createElement('a'); link.href = url; link.download = 'depositflow-import-template.csv'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function ImportRecords() {
  const user = useUser(); const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const send = useMutation({
    mutationFn: (commit: boolean) => { const body = new FormData(); body.append('file', file!); body.append('commit', String(commit)); return api('/admin/import', { method: 'POST', body }) },
    onSuccess: result => { if (result.committed) qc.invalidateQueries() },
  })
  if (user.role !== 'admin') return <Notice>Administrator access is required for this page.</Notice>
  const result: Row | undefined = send.data
  return <>
    <PageHeader eyebrow="ADMINISTRATION" title="Import existing records" description="Bring security deposits recorded elsewhere into the portal from a CSV file."
      actions={<Button variant="outline" onClick={downloadTemplate}><Download size={16}/>Download template</Button>}/>
    <Notice>Every file is checked first and nothing is saved until you confirm. Only rows without problems are imported, and an instrument already in the portal is never imported twice. Imported cases start as submitted and go through the same checks; most will need their receipt uploaded.</Notice>
    <Panel title="1. Choose a file" subtitle={`Required columns: ${COLUMNS.slice(0, 10).join(', ')}. Optional: ${COLUMNS.slice(10).join(', ')}. Dates as YYYY-MM-DD; up to 2,000 rows.`}>
      <div className="upload-area"><FileUp size={31}/><div><strong>{file ? file.name : 'UTF-8 CSV file'}</strong><p>{file ? `${(file.size / 1024).toFixed(1)} KB` : 'Use the template to see the expected format.'}</p></div>
        <label className="btn btn-outline upload-button">Choose CSV<input type="file" accept=".csv,text/csv" onChange={e => { setFile(e.target.files?.[0] || null); send.reset() }}/></label>
        <Button disabled={!file || send.isPending} onClick={() => send.mutate(false)}>Check file</Button></div>
    </Panel>
    {send.error && <ErrorState error={send.error}/>}
    {result && <Panel title={result.committed ? '3. Import complete' : '2. Check results'} subtitle={`${result.rows} rows · ${result.ready} ${result.committed ? 'imported' : 'ready to import'} · ${result.errors} with problems`}
      actions={!result.committed && result.ready > 0 && <Button disabled={send.isPending} onClick={() => send.mutate(true)}><Upload size={16}/>Import {result.ready} record{result.ready === 1 ? '' : 's'}</Button>}>
      {result.committed && <div className="padded"><div className="notice success"><CheckCircle2 size={18}/>Imported {result.ready} record{result.ready === 1 ? '' : 's'}. Rows with problems were skipped; fix them and import the file again.</div></div>}
      <div className="table-scroll"><table><thead><tr><th>Row</th><th>Institution</th><th>Instrument</th><th>Result</th><th>Problems</th></tr></thead><tbody>
        {result.results.map((r: Row) => <tr key={r.row}><td className="tabular">{r.row}</td><td>{r.institution_code}</td><td>{r.reference ? <Link className="record-link" to="/app/deposits">{r.number}</Link> : r.number}<span className="cell-subtitle">{r.reference}</span></td>
          <td><Badge value={r.status === 'error' ? 'rejected' : r.status === 'imported' ? 'completed' : 'pending'}>{r.status === 'error' ? 'Has problems' : r.status === 'imported' ? 'Imported' : 'Ready'}</Badge></td>
          <td>{r.errors.length ? <ul className="row-errors">{r.errors.map((e: string) => <li key={e}>{e}</li>)}</ul> : '—'}</td></tr>)}
      </tbody></table></div>
    </Panel>}
  </>
}
