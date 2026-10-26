import { useState, type ReactNode } from 'react'
import { ArrowUpRight, CheckCircle2, Loader2, AlertTriangle, Inbox, X } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from './ui/button'
import { Dialog } from './ui/dialog'
import { label } from '@/lib/utils'
import type { Row } from '@/lib/api'

export function Badge({ value, children }: { value: string; children?: ReactNode }) {
  const color = /officially_confirmed|approved|completed|resolved|active|authorised/.test(value) ? 'green' : /mock/.test(value) ? 'purple' : /failed|high|rejected|overdue|mismatched/.test(value) ? 'red' : /pending|warning|clarification|review|queued|matured|proposed/.test(value) ? 'amber' : 'blue'
  return <span className={`badge ${color}`}><i/>{children || label(value)}</span>
}
// The level is always written out, so the dot's colour never carries the meaning alone.
export function RiskBadge({ risk }: { risk?: Row | null }) {
  if (!risk) return <span className="cell-subtitle">Not scored</span>
  return <span className={`risk-badge ${risk.level}`} title="Orders review work. Not a finding of fraud."><i/>{Math.round(risk.score)} · {label(risk.level)}</span>
}
export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) { return <div className="page-heading"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="actions">{actions}</div>}</div> }
export function Panel({ title, subtitle, actions, children, className = '' }: { title?: string; subtitle?: string; actions?: ReactNode; children: ReactNode; className?: string }) { return <section className={`panel ${className}`}>{title && <div className="panel-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{actions}</div>}{children}</section> }
export function Loading() { return <div className="loading"><Loader2 className="spin" size={24}/> Loading portal records…</div> }
export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) { return <div role="alert" className="notice error"><AlertTriangle size={20}/><div><strong>Unable to complete this request</strong><p>{error instanceof Error ? error.message : 'An unexpected error occurred.'}</p>{retry && <Button variant="outline" onClick={retry}>Try again</Button>}</div></div> }
export function Empty({ title = 'No records to show', message = 'Records will appear here when an action is recorded.', action }: { title?: string; message?: string; action?: ReactNode }) { return <div className="empty"><Inbox size={32}/><h3>{title}</h3><p>{message}</p>{action}</div> }
export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: string }) { return <div className={`notice ${tone}`}><AlertTriangle size={18}/><div>{children}</div></div> }
export function Stat({ title, value, detail, icon, accent = '' }: { title: string; value: ReactNode; detail: string; icon: ReactNode; accent?: string }) { return <div className={`stat-card ${accent}`}><div className="stat-top"><span>{title}</span><span className="stat-icon">{icon}</span></div><div className="stat-value">{value}</div><div className="stat-detail"><span className="status-dot"/>{detail}</div></div> }
export interface ActionField { name: string; label: string; type?: string; options?: { value: string; label: string }[]; value?: string; required?: boolean; minLength?: number; help?: string }
export function ActionDialog({ open, onClose, title, description, fields, action, onSuccess, submitLabel = 'Save record' }: { open: boolean; onClose: () => void; title: string; description?: string; fields: ActionField[]; action: (data: Record<string, string>) => Promise<unknown>; onSuccess?: () => void; submitLabel?: string }) {
  const qc = useQueryClient()
  const mutation = useMutation({ mutationFn: action, onSuccess: () => { qc.invalidateQueries(); onSuccess?.(); onClose() } })
  return <Dialog open={open} onOpenChange={v => { if (!v && !mutation.isPending) onClose() }} title={title} description={description}><form className="form-stack" onSubmit={e => { e.preventDefault(); mutation.mutate(Object.fromEntries(new FormData(e.currentTarget).entries()) as Record<string, string>) }}>{fields.map(field => field.type === 'checkbox' ? <label key={field.name} className="check-field"><input name={field.name} type="checkbox" required={field.required !== false}/>{field.label}</label> : <label key={field.name} className="field">{field.label}{field.type === 'textarea' ? <textarea name={field.name} required={field.required !== false} minLength={field.minLength || 5} defaultValue={field.value} rows={3}/> : field.options ? <select name={field.name} defaultValue={field.value} required={field.required !== false}>{field.options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select> : <input name={field.name} type={field.type || 'text'} required={field.required !== false} minLength={field.minLength} defaultValue={field.value}/>} {field.help && <small>{field.help}</small>}</label>)}{mutation.error && <ErrorState error={mutation.error}/>}<div className="dialog-footer"><Button type="button" variant="outline" onClick={onClose} disabled={mutation.isPending}>Cancel</Button><Button disabled={mutation.isPending}>{mutation.isPending && <Loader2 className="spin" size={16}/>} {submitLabel}</Button></div></form></Dialog>
}
export function useAction() {
  const [message, setMessage] = useState(''); const [error, setError] = useState<unknown>(null); const qc = useQueryClient()
  const mutation = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: () => { setError(null); setMessage('Action recorded successfully.'); qc.invalidateQueries() }, onError: error => { setMessage(''); setError(error) } })
  const feedback = <>{message && <div className="notice success" role="status"><CheckCircle2 size={18}/>{message}<button className="icon-button" onClick={() => setMessage('')} aria-label="Dismiss notification"><X size={16}/></button></div>}{error ? <ErrorState error={error}/> : null}</>
  return { run: mutation.mutate, busy: mutation.isPending, feedback }
}
export function ExternalArrow() { return <ArrowUpRight size={16}/> }
