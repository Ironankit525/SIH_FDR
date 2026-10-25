import { useQuery } from '@tanstack/react-query'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type Row } from '@/lib/api'
import { dateLabel, label } from '@/lib/utils'
import { Empty, ErrorState, Loading, Notice, Panel, RiskBadge } from './common'

const THRESHOLDS = [['Medium', 20], ['High', 50], ['Critical', 80]] as const

function reviewState(signal: Row) {
  if (signal.discount === 1) return signal.task_status ? `Review task ${label(signal.task_status).toLowerCase()}` : 'Observation (no review task)'
  if (signal.discount === 0.5) return signal.task_status === 'resolution_proposed' ? 'Resolution proposed · counts half' : 'Condition no longer detected · counts half'
  if (signal.discount === 0.1) return 'Resolution confirmed by a second officer or Vigilance · counts 10%'
  return 'Resolved by one officer · counts 20%'
}

export function RiskPanel({ depositId }: { depositId: string }) {
  const query = useQuery<Row>({ queryKey: ['risk', depositId], queryFn: () => api(`/deposits/${depositId}/risk`) })
  if (query.isPending) return <Loading/>
  if (query.error) return <ErrorState error={query.error}/>
  const risk = query.data!
  // Assessments can be minutes apart, so the axis shows the time as well as the date.
  const history = risk.history.map((h: Row) => ({ ...h, score: Number(h.score), label: new Date(h.created_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) }))
  if (risk.level === 'none') return <>
    <Notice>{risk.notice} Institutions cannot see this tab.</Notice>
    <Panel title="No suspicious findings" subtitle={`Engine ${risk.engine_version} · weight policy v${risk.weights_version} · checked ${dateLabel(risk.created_at)}`}>
      <div className="padded"><p>The score appears only when something suspicious is found: altered or reused documents, a duplicate instrument, or evidence that contradicts the declaration. A bank that has not confirmed yet, or paperwork still missing, is not suspicion; those are listed as requirements on the case and block verification until they are met.</p></div>
    </Panel>
  </>
  return <>
    <Notice>{risk.notice} Institutions cannot see this tab.</Notice>
    <Panel title="Risk score" subtitle={`Engine ${risk.engine_version} · weight policy v${risk.weights_version} · scored ${dateLabel(risk.created_at)}`}>
      <div className="padded risk-hero"><strong>{Math.round(Number(risk.score))}</strong><div><RiskBadge risk={{ score: Number(risk.score), level: risk.level }}/><span className="cell-subtitle">Out of 100. Medium from 20, high from 50, critical from 80. From 50 the case goes to the Vigilance cell and the case officer cannot clear it.</span></div></div>
    </Panel>
    <div className="risk-columns">
      <Panel title="What is driving the score" subtitle="Each bar: points the score would lose without that signal">
        <div className="padded">{!risk.signals.length ? <Empty title="No risk signals" message="No review task or observation currently adds to this case's score."/> :
          <ul className="signal-list">{risk.signals.map((s: Row, i: number) => <li key={`${s.key}-${s.task_id ?? i}`} className="signal-row">
            <p>{s.explanation}</p><span className="signal-points">−{s.contribution.toFixed(1)} pts</span>
            <div className="signal-track" role="img" aria-label={`${s.contribution.toFixed(1)} of ${Number(risk.score).toFixed(1)} points`}><span style={{ width: `${Math.min(100, (s.contribution / Math.max(Number(risk.score), 1)) * 100)}%` }}/></div><span/>
            <small>{label(s.category)} · {label(s.source)} · {reviewState(s)}</small>
          </li>)}</ul>}
        </div>
      </Panel>
      <Panel title="Score history" subtitle="A new point is recorded whenever the evidence or its review changes">
        <div className="padded">{history.length < 2 ? <p className="cell-subtitle">One assessment so far: {Math.round(Number(risk.score))} ({label(risk.level)}).</p> :
          <div className="chart-container" style={{ height: 220 }}><ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 10, right: 56, left: -20, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#edf0f4"/>
              <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: '#d5dce5' }} fontSize={11} minTickGap={24}/>
              <YAxis domain={[0, 100]} ticks={[0, 20, 50, 80, 100]} tickLine={false} axisLine={false} fontSize={11}/>
              {THRESHOLDS.map(([name, value]) => <ReferenceLine key={name} y={value} stroke="#e1e6ee" label={{ value: name, position: 'right', fontSize: 10, fill: '#7a8ca0' }}/>)}
              <Tooltip formatter={(value, _name, item) => [`${value} · ${label(item.payload.level)}`, 'Score']} labelFormatter={(_l, items) => items?.[0] ? new Date(items[0].payload.created_at).toLocaleString('en-IN') : ''}/>
              <Line isAnimationActive={false} type="monotone" dataKey="score" stroke="#0071e3" strokeWidth={2} dot={{ r: 4, fill: '#0071e3', stroke: '#fff', strokeWidth: 2 }} activeDot={{ r: 6, stroke: '#fff', strokeWidth: 2 }}/>
            </LineChart>
          </ResponsiveContainer></div>}
        </div>
      </Panel>
    </div>
  </>
}
