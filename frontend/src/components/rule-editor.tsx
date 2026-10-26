import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, Plus, Trash2 } from 'lucide-react'
import { post, type Row } from '@/lib/api'
import { label } from '@/lib/utils'
import { Button } from './ui/button'
import { ErrorState, Panel } from './common'

const LEVELS = ['undergraduate', 'postgraduate', 'diploma']
const OWNERSHIP = ['government', 'government_aided', 'private']
interface Amount { programme: string; level: string; amount: string }

function problems(amounts: Amount[], multiplier: string, from: string, to: string, source: string) {
  const found: string[] = []
  const keys = amounts.map(a => `${a.programme.trim()}|${a.level}`)
  if (!amounts.length) found.push('Add at least one programme amount.')
  if (amounts.some(a => !a.programme.trim())) found.push('Every amount needs a programme name.')
  if (new Set(keys).size !== keys.length) found.push('Each programme and level may appear only once.')
  if (amounts.some(a => a.amount === '' || !(Number(a.amount) >= 0))) found.push('Amounts must be zero or more.')
  if (!(Number(multiplier) >= 1 && Number(multiplier) <= 10)) found.push('The private lease multiplier must be between 1 and 10.')
  if (!from || !to || to < from) found.push('The effective period must end on or after it starts.')
  if (source.trim().length < 10) found.push('Explain the source and applicability in at least 10 characters.')
  return found
}

export function RuleEditor({ base, onDone }: { base: Row; onDone: () => void }) {
  const qc = useQueryClient()
  const [amounts, setAmounts] = useState<Amount[]>(Object.entries(base.config.amounts as Record<string, number>).map(([key, amount]) => {
    const [programme, level] = key.split('|'); return { programme, level, amount: String(amount) }
  }))
  const [exempt, setExempt] = useState<string[]>(base.config.exempt_ownership)
  const [multiplier, setMultiplier] = useState(String(base.config.private_lease_multiplier))
  const [from, setFrom] = useState(base.effective_from); const [to, setTo] = useState(base.effective_to)
  const [source, setSource] = useState(base.source_reference); const [illustrative, setIllustrative] = useState<boolean>(base.illustrative)
  const issues = problems(amounts, multiplier, from, to, source)
  const mutation = useMutation({
    mutationFn: () => post('/admin/rules', { rule_id: base.rule_id, effective_from: from, effective_to: to, source_reference: source, illustrative,
      config: { amounts: Object.fromEntries(amounts.map(a => [`${a.programme.trim()}|${a.level}`, Number(a.amount)])), exempt_ownership: exempt, private_lease_multiplier: Number(multiplier) } }),
    onSuccess: () => { qc.invalidateQueries(); onDone() },
  })
  const setAmount = (index: number, part: keyof Amount, value: string) => setAmounts(list => list.map((a, i) => i === index ? { ...a, [part]: value } : a))
  return <Panel title={`Propose a new version of “${base.title}”`} subtitle={`Starting from version ${base.version}. A different administrator must approve it before it applies.`}>
    <form className="form-stack padded" onSubmit={e => { e.preventDefault(); if (!issues.length) mutation.mutate() }}>
      <fieldset><legend>Required amount by programme and level (INR)</legend>
        <div className="rule-rows">{amounts.map((a, i) => <div className="rule-row" key={i}>
          <label className="field">Programme<input value={a.programme} onChange={e => setAmount(i, 'programme', e.target.value)}/></label>
          <label className="field">Level<select value={a.level} onChange={e => setAmount(i, 'level', e.target.value)}>{LEVELS.map(l => <option key={l} value={l}>{label(l)}</option>)}</select></label>
          <label className="field">Amount<input type="number" min={0} step={1000} value={a.amount} onChange={e => setAmount(i, 'amount', e.target.value)}/></label>
          <Button type="button" variant="ghost" size="sm" aria-label={`Remove ${a.programme || 'row'} ${a.level}`} onClick={() => setAmounts(list => list.filter((_, j) => j !== i))}><Trash2 size={15}/></Button>
        </div>)}</div>
        <Button type="button" variant="outline" size="sm" onClick={() => setAmounts(list => [...list, { programme: '', level: 'undergraduate', amount: '' }])}><Plus size={15}/>Add programme</Button>
      </fieldset>
      <fieldset><legend>Ownership types exempt from a deposit</legend>{OWNERSHIP.map(o => <label className="check-field" key={o}><input type="checkbox" checked={exempt.includes(o)} onChange={e => setExempt(list => e.target.checked ? [...list, o] : list.filter(x => x !== o))}/>{label(o)}</label>)}</fieldset>
      <div className="rule-row"><label className="field">Private lease multiplier<input type="number" min={1} max={10} step={0.5} value={multiplier} onChange={e => setMultiplier(e.target.value)}/></label>
        <label className="field">Effective from<input type="date" value={from} onChange={e => setFrom(e.target.value)}/></label>
        <label className="field">Effective to<input type="date" value={to} onChange={e => setTo(e.target.value)}/></label></div>
      <label className="field">Source and applicability<textarea rows={3} value={source} onChange={e => setSource(e.target.value)}/></label>
      <label className="check-field"><input type="checkbox" checked={illustrative} onChange={e => setIllustrative(e.target.checked)}/>Illustrative rule: an officer must confirm applicability on every case</label>
      {issues.length > 0 && <div role="alert" className="notice error"><CircleAlert size={18}/><div>{issues.map(i => <p key={i}>{i}</p>)}</div></div>}
      {mutation.error && <ErrorState error={mutation.error}/>}
      <div className="actions"><Button disabled={issues.length > 0 || mutation.isPending}>Submit for approval</Button><Button type="button" variant="ghost" onClick={onDone}>Cancel</Button></div>
    </form>
  </Panel>
}
