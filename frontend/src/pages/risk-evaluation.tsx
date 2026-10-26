import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { api, type Row } from '@/lib/api'
import { dateLabel, label } from '@/lib/utils'
import { Empty, ErrorState, Loading, Notice, PageHeader, Panel } from '@/components/common'

const percent = (value: number | null | undefined) => value == null ? '—' : `${Math.round(value * 100)}%`

function CaseList({ rows }: { rows: Row[] }) {
  if (!rows.length) return <Empty title="None" message="No cases fall in this group."/>
  return <div className="table-scroll"><table><thead><tr><th>Case</th><th>Kind</th><th>Score</th><th>Signals</th></tr></thead>
    <tbody>{rows.map(r => <tr key={r.id}><td className="mono">{r.id}</td><td>{label(r.kind)}</td><td className="tabular">{Math.round(r.score)}</td><td>{r.signals.map(label).join(', ') || '—'}</td></tr>)}</tbody></table></div>
}

export function RiskEvaluation() {
  const query = useQuery<Row>({ queryKey: ['risk-evaluation-details'], queryFn: () => api('/risk/evaluation/details'), retry: false })
  if (query.isPending) return <Loading/>
  if (query.error) return <ErrorState error={query.error}/>
  const e = query.data!; const m = e.metrics; const intake = m.stages.intake; const bank = m.stages.after_bank_check
  const kinds = Object.entries(e.kinds as Record<string, Row>).filter(([kind]) => bank.per_kind[kind])
  return <>
    <Link to="/app" className="back-link"><ArrowLeft size={15}/>Back to overview</Link>
    <PageHeader eyebrow="Risk engine" title="Evaluation results" description={`${m.cases} synthetic cases (${m.problem_cases} with problems, ${m.genuine_cases} genuine) · evaluated ${dateLabel(e.generated_on)} · engine ${e.engine_version} · seed ${e.corpus.seed}`}/>
    <Notice>{e.notice} Medium means a score of {m.thresholds.medium} or more; high means {m.thresholds.high} or more.</Notice>
    <Panel title="Headline">
      <div className="table-scroll"><table><thead><tr><th>Stage</th><th>AUC</th><th>Problem cases ≥ medium</th><th>Problem cases ≥ high</th><th>Genuine cases ≥ medium</th><th>Problem cases in top 10</th></tr></thead><tbody>
        {[['At intake (documents only)', intake], ['After the bank check', bank]].map(([name, s]: any) => <tr key={name}><td><strong>{name}</strong></td><td className="tabular">{s.auc}</td><td className="tabular">{percent(s.recall_at_medium)}</td><td className="tabular">{percent(s.recall_at_high)}</td><td className="tabular">{percent(s.false_positive_rate_at_medium)}</td><td className="tabular">{percent(s.precision_at_10)}</td></tr>)}
      </tbody></table></div>
      <p className="padded cell-subtitle">AUC is the chance that a random problem case scores above a random genuine one: 0.5 is guessing, 1.0 is perfect separation.</p>
    </Panel>
    <Panel title="By kind of case" subtitle="For genuine kinds, lower score percentages are better. Declared non-compliance is not scored; it must be stopped by a requirement that blocks verification">
      <div className="table-scroll"><table><thead><tr><th>Kind</th><th>What it represents</th><th>Cases</th><th>≥ medium at intake</th><th>≥ medium after bank check</th><th>≥ high after bank check</th><th>Stopped by a requirement</th></tr></thead><tbody>
        {kinds.map(([kind, info]) => <tr key={kind}><td><strong>{label(kind)}</strong><span className="cell-subtitle">{info.compliance ? 'Declared non-compliance · not scored' : info.problem ? 'Suspicious' : 'Genuine'}</span></td><td>{info.description}</td><td className="tabular">{bank.per_kind[kind].cases}</td><td className="tabular">{percent(intake.per_kind[kind].at_least_medium)}</td><td className="tabular">{percent(bank.per_kind[kind].at_least_medium)}</td><td className="tabular">{percent(bank.per_kind[kind].at_least_high)}</td><td className="tabular">{percent(bank.per_kind[kind].stopped_by_requirement)}</td></tr>)}
      </tbody></table></div>
    </Panel>
    <div className="two-columns">
      <Panel title="Suspicious cases still below medium" subtitle="After the bank check"><CaseList rows={e.misses}/></Panel>
      <Panel title="Genuine cases at medium or above" subtitle="After the bank check"><CaseList rows={e.false_alarms}/></Panel>
    </div>
    <Panel title="Which signals fired" subtitle="After the bank check · precision is the share of cases with the signal that had a real problem">
      <div className="table-scroll"><table><thead><tr><th>Signal</th><th>Problem cases</th><th>Genuine cases</th><th>Precision</th></tr></thead><tbody>
        {Object.entries(bank.detectors as Record<string, Row>).map(([key, d]) => <tr key={key}><td>{label(key)}</td><td className="tabular">{d.problem_cases}</td><td className="tabular">{d.genuine_cases}</td><td className="tabular">{percent(d.precision)}</td></tr>)}
      </tbody></table></div>
    </Panel>
  </>
}
