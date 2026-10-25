import type { Row } from '@/lib/api'
import { Badge } from './common'

export function CaseProgress({ deposit, role }: { deposit: Row; role: string }) {
  const tasks = deposit.discrepancies.filter((task: Row) => task.status !== 'resolved')
  const pendingDocuments = deposit.documents.filter((doc: Row) => doc.instrument_id === deposit.instrument.id && ['queued', 'processing'].includes(doc.processing_status))
  const release = deposit.release
  const verified = deposit.instrument.verification_status === 'officially_confirmed' || (deposit.mock_verification_permitted && deposit.instrument.verification_status === 'mock_confirmed')
  const steps = [
    { name: 'Submitted', done: !!deposit.submitted_at },
    { name: 'Evidence reviewed', done: verified && tasks.length === 0 && pendingDocuments.length === 0 },
    { name: 'Clearances', done: !!release && release.workflow_snapshot.cells.every((cell: string) => release.clearances.some((item: Row) => item.cell === cell && item.status === 'approved')) },
    { name: 'Authority approval', done: ['authorised', 'completed'].includes(release?.status) },
    { name: 'Completion recorded', done: release?.status === 'completed' },
  ]
  const current = steps.findIndex(step => !step.done)
  const priority = tasks.some((task: Row) => task.severity === 'high') ? 'High priority review' : tasks.length ? 'Review needed' : 'No open review tasks'
  let next = 'Review the evidence and the outstanding tasks below.'
  if (release?.status === 'completed') next = 'The completion reference is recorded. Evidence and history remain available.'
  else if (release?.status === 'authorised') next = 'The authority can now record the external NOC or completion reference.'
  else if (release?.status === 'rejected') next = 'The authority rejected this release request. Read the recorded decision and reasons.'
  else if (release?.status === 'returned') next = 'The institution must address the authority’s comments and resubmit the request.'
  else if (deposit.status === 'draft') next = 'Upload the instrument receipt, check its details, then submit the case.'
  else if (pendingDocuments.length) next = 'Receipt extraction is in progress. The results will appear automatically.'
  else if (role === 'institution' && tasks.length) next = 'Open Review tasks to respond to the officer’s questions and provide supporting evidence.'
  else if (role === 'verification') next = 'Assign the case to yourself, check the original evidence and resolve each review task with a reason.'
  else if (role === 'clearance') next = 'Open Release workflow to record the decision for your assigned clearance cell.'
  else if (role === 'authority') next = 'Check the release blockers. Final approval requires a different officer from those who submitted or reviewed this case.'
  else if (role === 'institution' && !release) next = 'Bank verification and officer review must be completed before release can be authorised.'

  return <section className="case-progress" aria-label="Case progress">
    <ol>{steps.map((step, index) => <li key={step.name} className={step.done ? 'done' : index === current ? 'current' : ''} aria-current={index === current ? 'step' : undefined}>
      <span aria-hidden="true">{step.done ? '✓' : index + 1}</span><div>{step.name}<small>{step.done ? 'Complete' : 'Pending'}</small></div>
    </li>)}</ol>
    <div className="case-next-action"><Badge value={tasks.length ? 'warning' : 'completed'}>{priority}</Badge><p>{next}</p></div>
  </section>
}
