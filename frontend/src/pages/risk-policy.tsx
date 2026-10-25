import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, CircleAlert, Gauge, History, Layers, Pencil, Scale, X } from 'lucide-react'
import { useUser } from '@/App'
import { api, post, type Row } from '@/lib/api'
import { dateLabel, label } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ActionDialog, type ActionField, Badge, Empty, ErrorState, Loading, Notice, PageHeader, Panel, Stat } from '@/components/common'

const CATEGORIES = ['identity', 'document_integrity', 'financial', 'coverage', 'duplication', 'verification', 'behaviour', 'process']
const LEVELS = ['low', 'medium', 'high', 'critical']
type Thresholds = { medium: string; high: string; critical: string }
interface Draft { weights: Record<string, string>; caps: Record<string, string>; thresholds: Thresholds }
interface Policy { weights: Record<string, number>; category_caps: Record<string, number>; thresholds: Record<string, number> }
interface Modal { title: string; description?: string; fields: ActionField[]; action: (data: Record<string, string>) => Promise<unknown>; onSuccess?: () => void; submitLabel?: string }

function Level({ value }: { value: string }) { return <span className={`risk-badge ${value}`}><i/>{label(value)}</span> }

function draftFrom(active: Row): Draft {
  return {
    weights: Object.fromEntries(Object.entries(active.weights).map(([key, value]) => [key, String(value)])),
    caps: Object.fromEntries(CATEGORIES.map(c => [c, active.category_caps[c] == null ? '' : String(active.category_caps[c])])),
    thresholds: { medium: String(active.thresholds.medium), high: String(active.thresholds.high), critical: String(active.thresholds.critical) },
  }
}

function toPolicy(draft: Draft): Policy {
  return {
    weights: Object.fromEntries(Object.entries(draft.weights).map(([key, value]) => [key, Number(value)])),
    category_caps: Object.fromEntries(Object.entries(draft.caps).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value)])),
    thresholds: { medium: Number(draft.thresholds.medium), high: Number(draft.thresholds.high), critical: Number(draft.thresholds.critical) },
  }
}

// Mirrors the server's validation so problems show before anything is sent.
function problems(draft: Draft) {
  const found: string[] = []
  const bad = Object.entries(draft.weights).filter(([, v]) => v === '' || !(Number(v) >= 0 && Number(v) <= 0.95)).map(([k]) => label(k))
  if (bad.length) found.push(`Weights must be between 0 and 0.95: ${bad.join(', ')}.`)
  if (Object.values(draft.caps).some(v => v !== '' && !(Number(v) > 0 && Number(v) <= 1))) found.push('Category caps must be above 0 and at most 1, or empty for no cap.')
  const t = toPolicy(draft).thresholds
  if (!(t.medium > 0 && t.medium < t.high && t.high < t.critical && t.critical < 100)) found.push('Thresholds must rise: 0 < medium < high < critical < 100.')
  return found
}

function differences(version: Row, signals: Record<string, Row>) {
  const lines = Object.entries(version.weights as Record<string, number>).filter(([key, value]) => signals[key] && signals[key].default_weight !== value)
    .map(([key, value]) => `${label(key)}: ${signals[key].default_weight} → ${value}`)
  const t = version.thresholds
  if (t.medium !== 20 || t.high !== 50 || t.critical !== 80) lines.push(`Thresholds: medium ${t.medium}, high ${t.high}, critical ${t.critical}`)
  const caps = Object.entries(version.category_caps as Record<string, number>).map(([c, v]) => `${label(c)} ${Math.round(v * 100)}`).join(', ')
  if (caps !== 'Behaviour 15') lines.push(`Category caps: ${caps || 'none'}`)
  return lines
}

export function RiskPolicy() {
  const user = useUser(); const admin = user.role === 'admin'
  const query = useQuery<Row>({ queryKey: ['risk-weights'], queryFn: () => api('/admin/risk-weights'), enabled: admin || user.role === 'auditor' })
  const [draft, setDraft] = useState<Draft | null>(null)
  const [modal, setModal] = useState<Modal | null>(null)
  const [previewing, setPreviewing] = useState('')
  const preview = useMutation({ mutationFn: (policy: Policy) => post('/admin/risk-weights/preview', policy) })
  if (!admin && user.role !== 'auditor') return <Notice>Administrator or auditor access is required for this page.</Notice>
  if (query.isPending) return <Loading/>
  if (query.error) return <ErrorState error={query.error}/>
  const data = query.data!; const active = data.active; const signals: Record<string, Row> = data.signals
  const pending = data.versions.filter((v: Row) => v.status === 'proposed')
  const current = data.versions.find((v: Row) => v.status === 'active')
  const issues = draft ? problems(draft) : []
  const shown = draft ? toPolicy(draft) : active
  const runPreview = (policy: Policy, title: string) => { setPreviewing(title); preview.mutate(policy) }
  const set = (part: 'weights' | 'caps' | 'thresholds', key: string, value: string) => setDraft(d => d && ({ ...d, [part]: { ...d[part], [key]: value } }))
  const submit = () => setModal({
    title: 'Propose this risk policy', submitLabel: 'Submit for approval',
    description: 'A different administrator must approve it. Approval rescores every case under the new policy.',
    fields: [{ name: 'notes', label: 'Reason for the change', type: 'textarea', minLength: 10 }],
    action: values => post('/admin/risk-weights', { ...toPolicy(draft!), notes: values.notes }),
    onSuccess: () => { setDraft(null); preview.reset() },
  })
  const approve = (version: Row) => setModal({
    title: `Approve risk policy version ${version.version}`, submitLabel: 'Approve and rescore',
    description: 'Every case is rescored under this policy as soon as you approve. Preview its impact first if you have not.',
    fields: [{ name: 'notes', label: 'Approval rationale', type: 'textarea', minLength: 5 }],
    action: values => post(`/admin/risk-weights/${version.id}/approve`, values),
    onSuccess: () => preview.reset(),
  })

  return <>
    <PageHeader eyebrow="Administration" title="Risk policy" description="The weights, caps and thresholds that turn review findings into a risk score."
      actions={admin && (draft ? <Button variant="outline" onClick={() => { setDraft(null); preview.reset() }}><X size={16}/>Discard draft</Button>
        : <Button onClick={() => setDraft(draftFrom(active))}><Pencil size={16}/>Propose changes</Button>)}/>
    <Notice>A score orders review work; it never approves or refuses a case. Every change needs a second administrator's approval, and approval rescores all cases. {admin ? '' : 'Auditors have read-only access.'}</Notice>
    <div className="stats-grid">
      <Stat title="Active policy" value={`v${active.version}`} detail={active.version === 0 ? 'Built-in defaults' : `Approved by ${current?.approved_by_name ?? 'an administrator'}`} icon={<Scale size={18}/>}/>
      <Stat title="Level thresholds" value={<span className="stat-compact">{shown.thresholds.medium} / {shown.thresholds.high} / {shown.thresholds.critical}</span>} detail="Medium / high / critical score" icon={<Gauge size={18}/>}/>
      <Stat title="Category caps" value={String(Object.keys(shown.category_caps).length)} detail={Object.entries(shown.category_caps).map(([c, v]) => `${label(c)} ≤ ${Math.round(Number(v) * 100)} pts`).join(', ') || 'No caps'} icon={<Layers size={18}/>}/>
      <Stat title="Awaiting approval" value={String(pending.length)} detail={`Engine ${data.engine_version}`} icon={<History size={18}/>}/>
    </div>

    {draft && <Panel title="Levels and caps" subtitle="Draft · not yet proposed">
      <div className="padded policy-controls">
        <fieldset><legend>Score thresholds</legend>{(['medium', 'high', 'critical'] as const).map(name => <label className="field" key={name}>{label(name)} from<input type="number" min={1} max={99} value={draft.thresholds[name]} onChange={e => set('thresholds', name, e.target.value)}/></label>)}</fieldset>
        <fieldset><legend>Category caps (0–1; empty means no cap)</legend><div className="cap-grid">{CATEGORIES.map(c => <label className="field" key={c}>{label(c)}<input type="number" min={0} max={1} step={0.05} placeholder="No cap" value={draft.caps[c]} onChange={e => set('caps', c, e.target.value)}/></label>)}</div></fieldset>
        {issues.length > 0 && <div role="alert" className="notice error"><CircleAlert size={18}/><div>{issues.map(i => <p key={i}>{i}</p>)}</div></div>}
        <div className="actions"><Button variant="outline" disabled={issues.length > 0 || preview.isPending} onClick={() => runPreview(toPolicy(draft), 'your draft')}>Preview impact</Button><Button disabled={issues.length > 0} onClick={submit}>Submit for approval</Button></div>
      </div>
    </Panel>}

    {(preview.data || preview.isPending || preview.error) && <Panel title={`Impact of ${previewing}`} subtitle="Open cases, computed now. Nothing is stored." className="policy-preview">
      <div className="padded">{preview.isPending ? <Loading/> : preview.error ? <ErrorState error={preview.error}/> : <>
        <div className="table-scroll"><table><thead><tr><th>Level</th><th>Now</th><th>With this policy</th><th>Change</th></tr></thead><tbody>
          {LEVELS.map(level => { const now = preview.data.current[level]; const next = preview.data.proposed[level]; return <tr key={level}><td><Level value={level}/></td><td className="tabular">{now}</td><td className="tabular">{next}</td><td className="tabular">{next - now > 0 ? `+${next - now}` : next - now || '—'}</td></tr> })}
        </tbody></table></div>
        <p className="cell-subtitle">{preview.data.changed} of {preview.data.cases} cases would change level.</p>
        {preview.data.changes.length > 0 && <ul className="change-list">{preview.data.changes.map((c: Row) => <li key={c.deposit_id}><Link className="record-link" to={`/app/deposits/${c.deposit_id}`}>{c.reference}</Link><span>{c.institution}</span><span className="change-levels"><Level value={c.from_level}/> {Math.round(c.from_score)} <ArrowRight size={13}/> <Level value={c.to_level}/> {Math.round(c.to_score)}</span></li>)}</ul>}
      </>}</div>
    </Panel>}

    <Panel title="Signal weights" subtitle={draft ? 'Draft · edit a weight to change how much its finding counts' : 'How much each finding can add to a score'}>
      <div className="table-scroll"><table><thead><tr><th>Signal</th><th>Weight</th><th>Default</th><th>Most it adds alone</th></tr></thead>
        {CATEGORIES.map(category => <tbody key={category}>
          <tr className="group-row"><td colSpan={4}>{label(category)}{shown.category_caps[category] != null && <span className="cell-subtitle">Capped at {Math.round(Number(shown.category_caps[category]) * 100)} points for the whole category</span>}</td></tr>
          {Object.entries(signals).filter(([, s]) => s.category === category).map(([key, s]) => {
            const weight = draft ? draft.weights[key] : String(active.weights[key]); const changed = Number(weight) !== s.default_weight
            return <tr key={key}><td><strong>{label(key)}</strong>{s.strength < 1 && <span className="cell-subtitle">Evidence strength {s.strength}</span>}</td>
              <td>{draft ? <input className="weight-input" aria-label={`Weight for ${label(key)}`} type="number" min={0} max={0.95} step={0.05} value={weight} onChange={e => set('weights', key, e.target.value)}/> : <span className="tabular">{weight}</span>}{changed && <span className="cell-subtitle">Changed from default</span>}</td>
              <td className="tabular">{s.default_weight}</td>
              <td className="tabular">{Number.isFinite(Number(weight)) ? `${Math.round(Number(weight) * s.strength * 100)} pts` : '—'}</td></tr>
          })}
        </tbody>)}
      </table></div>
    </Panel>

    <Panel title="Version history" subtitle="Version 0 is the built-in default policy">
      {!data.versions.length ? <Empty title="No proposals yet" message="The built-in default policy is in use."/> : <div className="padded stack">{data.versions.map((v: Row) => {
        const changes = differences(v, signals); const own = v.proposed_by === user.id
        return <article key={v.id} className="version-card">
          <div className="row-between"><h3>Version {v.version}</h3><Badge value={v.status}/></div>
          <p className="cell-subtitle">Proposed by {v.proposed_by_name ?? 'an administrator'} on {dateLabel(v.created_at)}{v.approved_by_name && ` · approved by ${v.approved_by_name}`}</p>
          <p>{v.notes}</p>
          {changes.length ? <ul className="diff-list">{changes.map(line => <li key={line}>{line}</li>)}</ul> : <p className="cell-subtitle">Same as the built-in defaults.</p>}
          {v.status === 'proposed' && <div className="actions">
            <Button variant="outline" size="sm" aria-label={`Preview impact of version ${v.version}`} disabled={preview.isPending} onClick={() => runPreview({ weights: v.weights, category_caps: v.category_caps, thresholds: v.thresholds }, `version ${v.version}`)}>Preview impact</Button>
            {admin && <Button size="sm" disabled={own} onClick={() => approve(v)}>{own ? 'Requires a different administrator' : 'Approve'}</Button>}
          </div>}
        </article>
      })}</div>}
    </Panel>
    {modal && <ActionDialog open onClose={() => setModal(null)} {...modal}/>}
  </>
}
