import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, ArrowRight, ArrowUpRight, Building2, CheckCircle2, CircleAlert,
  ClipboardCheck, Clock3, Eye, FileText, Filter, IndianRupee, Landmark,
  LockKeyhole, Search, ShieldAlert, ShieldCheck, XCircle, AlertTriangle, ChevronLeft, ChevronRight
} from 'lucide-react'
import { useUser } from '@/App'
import { api, post, type Row } from '@/lib/api'
import { dateLabel, money, label, verificationLabel } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Badge, Empty, ErrorState, Loading, Notice, PageHeader, Panel, Stat, useAction } from '@/components/common'

export function BankDashboard() {
  const user = useUser()
  const query = useQuery<Row>({ queryKey: ['bank-overview'], queryFn: () => api('/bank/overview') })
  const action = useAction()

  if (query.isPending) return <Loading/>
  if (query.error) return <ErrorState error={query.error}/>
  const d = query.data!

  return (
    <>
      <PageHeader
        eyebrow={user.bank_name || 'Bank Verification Portal'}
        title="Bank Verification Overview"
        description={`Welcome back, ${user.name.split(' ')[0]}. Manage and verify fixed deposit receipt requests forwarded by AICTE officers.`}
        actions={
          <Button asChild>
            <Link to="/app/bank/queue">
              <ClipboardCheck size={16}/>View verification queue
            </Link>
          </Button>
        }
      />
      {action.feedback}

      <div className="overview-banner">
        <div className="banner-icon"><Landmark size={24}/></div>
        <div>
          <strong>Official Bank Verification Gateway · {user.bank_name}</strong>
          <p>Verify institutional security deposits forwarded by AICTE officers directly against bank branch records.</p>
        </div>
        <span className="banner-date">{new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}</span>
      </div>

      <div className="stats-grid">
        <Stat
          title="Total requests received"
          value={String(d.total_requests).padStart(2, '0')}
          detail="All-time forwarded FDR requests"
          icon={<Landmark size={18}/>}
          accent="stat-featured"
        />
        <Stat
          title="Pending review"
          value={String(d.pending_requests).padStart(2, '0')}
          detail="Awaiting bank review"
          icon={<Clock3 size={18}/>}
        />
        <Stat
          title="Under verification"
          value={String(d.under_verification).padStart(2, '0')}
          detail="Currently being examined"
          icon={<ClipboardCheck size={18}/>}
        />
        <Stat
          title="Successfully verified"
          value={String(d.verified).padStart(2, '0')}
          detail="Confirmed against records"
          icon={<CheckCircle2 size={18}/>}
        />
        <Stat
          title="Rejected FDRs"
          value={String(d.rejected).padStart(2, '0')}
          detail="Mismatched or unconfirmed"
          icon={<XCircle size={18}/>}
        />
        <Stat
          title="Information requested"
          value={String(d.additional_info_required).padStart(2, '0')}
          detail="Clarification needed"
          icon={<CircleAlert size={18}/>}
        />
      </div>

      <div className="two-columns">
        <Panel
          title="Recent verification requests"
          subtitle="Latest FDRs forwarded for your review"
          actions={
            <Link className="text-link" to="/app/bank/queue">
              View complete queue <ArrowRight size={15}/>
            </Link>
          }
        >
          {!d.recent?.length ? (
            <Empty title="No requests received yet" message="When AICTE officers forward FDRs to your bank, they will appear here."/>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>FDR Reference</th>
                    <th>Institution</th>
                    <th>FDR Number</th>
                    <th>Deposit Amount</th>
                    <th>Status</th>
                    <th aria-label="Action"/>
                  </tr>
                </thead>
                <tbody>
                  {d.recent.map((r: Row) => (
                    <tr key={r.id}>
                      <td>
                        <Link className="record-link" to={`/app/bank/verifications/${r.id}`}>
                          {r.reference}
                        </Link>
                      </td>
                      <td>{r.institution_name}</td>
                      <td><code>{r.instrument_number}</code></td>
                      <td><strong>{money(r.amount)}</strong></td>
                      <td><Badge value={r.status}/></td>
                      <td>
                        <Link to={`/app/bank/verifications/${r.id}`} className="table-open" aria-label={`Open ${r.reference}`}>
                          <ArrowUpRight size={18}/>
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <div className="stack">
          <Panel title="Verification quick actions" subtitle="Filter verification tasks">
            <div className="action-list">
              {[
                { path: '/app/bank/queue?status=pending', name: 'Pending review', sub: 'New requests from officers', count: d.pending_requests, color: 'blue', icon: Clock3 },
                { path: '/app/bank/queue?status=under_verification', name: 'Under examination', sub: 'Cases currently in progress', count: d.under_verification, color: 'amber', icon: ClipboardCheck },
                { path: '/app/bank/queue?status=verified', name: 'Verified FDRs', sub: 'Confirmed records', count: d.verified, color: 'green', icon: CheckCircle2 },
                { path: '/app/bank/queue?status=additional_info_required', name: 'Clarifications requested', sub: 'Awaiting institution response', count: d.additional_info_required, color: 'purple', icon: CircleAlert },
              ].map(item => (
                <Link to={item.path} className="action-item" key={item.name}>
                  <span className={`action-icon ${item.color}`}><item.icon size={18}/></span>
                  <div>
                    <strong>{item.name}</strong>
                    <small>{item.sub}</small>
                  </div>
                  <b>{item.count}</b>
                  <ChevronRight size={16}/>
                </Link>
              ))}
            </div>
          </Panel>

          <div className="aside-note">
            <ShieldCheck size={22}/>
            <h3>Traceable Bank Verification</h3>
            <p>Every verification decision is timestamped and recorded in the immutable audit trail under your bank credentials.</p>
            <ul>
              <li>Original institution documents remain unalterable</li>
              <li>Rejections require an explanation for AICTE officers</li>
              <li>Requests for more information pause verification until answered</li>
            </ul>
          </div>
        </div>
      </div>
    </>
  )
}

export function BankQueue() {
  const user = useUser()
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [page, setPage] = useState(0)
  const pageSize = 8

  const params = new URLSearchParams(filters).toString()
  const query = useQuery<Row[]>({
    queryKey: ['bank-verifications', params],
    queryFn: () => api('/bank/verifications?' + params)
  })

  const rows = query.data || []
  const effectivePage = Math.min(page, Math.max(0, Math.ceil(rows.length / pageSize) - 1))
  const slice = rows.slice(effectivePage * pageSize, (effectivePage + 1) * pageSize)

  const update = (key: string, value: string) => {
    setFilters(f => ({ ...f, [key]: value }))
    setPage(0)
  }

  return (
    <>
      <PageHeader
        eyebrow={user.bank_name || 'Bank Portal'}
        title="Verification Queue"
        description={`Review, cross-check and verify institutional FDR submissions assigned to ${user.bank_name || 'your bank'}.`}
      />

      <Panel>
        <div className="table-toolbar">
          <div className="search-input">
            <Search size={17}/>
            <input
              aria-label="Search verification requests"
              placeholder="Search reference, institution, FDR number or depositor…"
              value={filters.q || ''}
              onChange={e => update('q', e.target.value)}
            />
          </div>

          <select
            aria-label="Filter by status"
            value={filters.status || ''}
            onChange={e => update('status', e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="sent">Forwarded / Pending</option>
            <option value="under_verification">Under verification</option>
            <option value="verified">Verified</option>
            <option value="rejected">Rejected</option>
            <option value="additional_info_required">Additional info required</option>
          </select>

          {Object.keys(filters).length > 0 && (
            <Button variant="ghost" onClick={() => { setFilters({}); setPage(0) }}>
              Clear filters
            </Button>
          )}
        </div>

        {query.isPending ? (
          <Loading/>
        ) : query.error ? (
          <ErrorState error={query.error}/>
        ) : !rows.length ? (
          <Empty
            title="No matching verification requests"
            message="No FDRs assigned to your bank match the selected filters."
          />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>FDR Reference / Institution</th>
                    <th>FDR Details</th>
                    <th>Deposit Amount</th>
                    <th>Maturity Date</th>
                    <th>Forwarded Date</th>
                    <th>Request Status</th>
                    <th aria-label="Action"/>
                  </tr>
                </thead>
                <tbody>
                  {slice.map(row => (
                    <tr key={row.id}>
                      <td>
                        <Link className="record-link" to={`/app/bank/verifications/${row.id}`}>
                          {row.reference}
                        </Link>
                        <span className="cell-subtitle">{row.institution_name} ({row.institution_code})</span>
                      </td>
                      <td>
                        <code>{row.instrument_number}</code>
                        <span className="cell-subtitle">{row.branch}</span>
                      </td>
                      <td>
                        <strong className="tabular">{money(row.amount)}</strong>
                        <span className="cell-subtitle">Depositor: {row.depositor_name}</span>
                      </td>
                      <td>
                        {dateLabel(row.maturity_date)}
                        {row.days_to_maturity != null && (
                          <span className={`cell-subtitle ${row.days_to_maturity < 0 ? 'text-red' : row.days_to_maturity <= 30 ? 'text-amber' : ''}`}>
                            {row.days_to_maturity < 0 ? `${Math.abs(row.days_to_maturity)}d past maturity` : `${row.days_to_maturity}d remaining`}
                          </span>
                        )}
                      </td>
                      <td>
                        {dateLabel(row.created_at)}
                        <span className="cell-subtitle">By {row.requested_by_name}</span>
                      </td>
                      <td>
                        <Badge value={row.status}/>
                        {row.bank_decision && row.bank_decision !== row.status && (
                          <span className="cell-subtitle">{label(row.bank_decision)}</span>
                        )}
                      </td>
                      <td>
                        <Button asChild size="sm" variant="outline">
                          <Link to={`/app/bank/verifications/${row.id}`}>
                            Review & Verify <ArrowUpRight size={14}/>
                          </Link>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="table-footer">
              <span>
                Showing {effectivePage * pageSize + 1}–{Math.min((effectivePage + 1) * pageSize, rows.length)} of {rows.length} requests
              </span>
              <div className="actions">
                <Button
                  size="sm"
                  variant="outline"
                  aria-label="Previous page"
                  disabled={effectivePage === 0}
                  onClick={() => setPage(effectivePage - 1)}
                >
                  <ChevronLeft size={16}/>
                </Button>
                <span>Page {effectivePage + 1}</span>
                <Button
                  size="sm"
                  variant="outline"
                  aria-label="Next page"
                  disabled={(effectivePage + 1) * pageSize >= rows.length}
                  onClick={() => setPage(effectivePage + 1)}
                >
                  <ChevronRight size={16}/>
                </Button>
              </div>
            </div>
          </>
        )}
      </Panel>
    </>
  )
}

export function BankVerificationDetail() {
  const { id } = useParams()
  const user = useUser()
  const qc = useQueryClient()
  const action = useAction()

  const [decision, setDecision] = useState<'verified' | 'rejected' | 'additional_info_required'>('verified')
  const [remarks, setRemarks] = useState('')
  const [confirmedAmount, setConfirmedAmount] = useState('')
  const [confirmedMaturity, setConfirmedMaturity] = useState('')
  const [viewer, setViewer] = useState<{ url: string; name: string; mime: string } | null>(null)

  const query = useQuery<Row>({
    queryKey: ['bank-verification-detail', id],
    queryFn: () => api(`/bank/verifications/${id}`)
  })

  const viewDoc = (docId: string, filename: string, mime: string) => {
    action.run(async () => {
      const data = await api(`/documents/${docId}/access`)
      setViewer({ url: data.url, name: filename, mime })
    })
  }

  const submitDecision = useMutation({
    mutationFn: () => {
      const payload: any = { decision, remarks }
      if (decision === 'verified' && (confirmedAmount || confirmedMaturity)) {
        payload.confirmed_fields = {
          amount: confirmedAmount ? Number(confirmedAmount) : undefined,
          maturity_date: confirmedMaturity || undefined,
        }
      }
      return post(`/bank/verifications/${id}/decision`, payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bank-verification-detail', id] })
      qc.invalidateQueries({ queryKey: ['bank-overview'] })
      qc.invalidateQueries({ queryKey: ['bank-verifications'] })
    }
  })

  if (query.isPending) return <Loading/>
  if (query.error) return <ErrorState error={query.error}/>
  const d = query.data!
  const req = d.request
  const inst = d.instrument
  const institution = d.institution
  const deposit = d.deposit

  const isFinalized = req.status === 'verified' || req.status === 'rejected' || !!req.bank_decision

  return (
    <>
      <Link to="/app/bank/queue" className="back-link">
        <ArrowLeft size={15}/>Back to verification queue
      </Link>

      <PageHeader
        eyebrow={`${institution.code} · ${user.bank_name || inst.bank}`}
        title={deposit.reference}
        description={`FDR Verification Request for ${institution.name}`}
        actions={
          <>
            <Badge value={req.status}/>
            {req.bank_decision && req.bank_decision !== req.status && (
              <Badge value={req.bank_decision}>{label(req.bank_decision)}</Badge>
            )}
          </>
        }
      />
      {action.feedback}

      <div className="case-summary">
        <div>
          <span>Deposit amount</span>
          <strong>{money(inst.amount)}</strong>
        </div>
        <div>
          <span>FDR Number</span>
          <code>{inst.number}</code>
        </div>
        <div>
          <span>Bank maturity</span>
          <strong>{dateLabel(inst.maturity_date)}</strong>
        </div>
        <div>
          <span>Verification status</span>
          <Badge value={req.status}>{verificationLabel(req.status)}</Badge>
        </div>
      </div>

      <div className="two-columns">
        <div className="stack">
          {/* FDR Instrument Details */}
          <Panel title="Instrument details" subtitle="Declared by institution and verified by AICTE officer">
            <div className="padded">
              <dl className="detail-list">
                {[
                  ['Instrument type', inst.instrument_type],
                  ['Bank name', inst.bank],
                  ['Branch name', inst.branch],
                  ['FDR reference number', inst.number],
                  ['Depositor name', inst.depositor_name],
                  ['Deposit amount', money(inst.amount)],
                  ['Issue date', dateLabel(inst.issue_date)],
                  ['Bank maturity date', dateLabel(inst.maturity_date)],
                  ['Validity date', dateLabel(inst.validity_date)],
                  ['Lien / security details', inst.lien_details || 'None specified'],
                ].map(([key, val]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{val}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </Panel>

          {/* Institution Information */}
          <Panel title="Institution information" subtitle="Registered institution requesting approval">
            <div className="padded">
              <dl className="detail-list">
                {[
                  ['Institution name', institution.name],
                  ['Institution code', institution.code],
                  ['State', institution.state],
                  ['Approved programme', institution.programme],
                  ['Contact email', institution.contact_email],
                  ['Address', institution.address || 'Knowledge Park'],
                ].map(([key, val]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{val}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </Panel>

          {/* Officer Verification Request Notes */}
          <Panel title="Officer forwarding notes" subtitle="Instructions from the reviewing AICTE officer">
            <div className="padded stack">
              <div>
                <strong>Forwarded by:</strong> {req.requested_by_name} on {dateLabel(req.created_at)}
              </div>
              {req.officer_notes ? (
                <div className="quoted-note">
                  <strong>Officer remarks</strong>
                  <p>{req.officer_notes}</p>
                </div>
              ) : (
                <p className="cell-subtitle">No additional officer notes provided.</p>
              )}
            </div>
          </Panel>

          {/* Uploaded Documents Vault */}
          <Panel title="Original submitted documents" subtitle="Inspect the original FDR certificate uploaded by the institution">
            {!d.documents?.length ? (
              <div className="padded"><p className="cell-subtitle">No documents attached.</p></div>
            ) : (
              <div className="document-list">
                {d.documents.map((doc: Row) => (
                  <article className="document-row" key={doc.id}>
                    <span className="document-icon"><FileText size={22}/></span>
                    <div className="document-meta">
                      <strong>{doc.filename}</strong>
                      <small>{label(doc.category)} · {(doc.size / 1024).toFixed(1)} KB · {dateLabel(doc.created_at)}</small>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => viewDoc(doc.id, doc.filename, doc.content_type)}
                    >
                      <Eye size={15}/>Preview document
                    </Button>
                  </article>
                ))}
              </div>
            )}
          </Panel>
        </div>

        {/* Verification Action Panel */}
        <div className="stack">
          {isFinalized ? (
            <Panel title="Verification decision recorded" subtitle="Audit-logged decision from your bank">
              <div className="padded stack">
                <div className="row-between">
                  <strong>Decision:</strong>
                  <Badge value={req.bank_decision || req.status}>
                    {label(req.bank_decision || req.status)}
                  </Badge>
                </div>

                <div>
                  <dt className="cell-subtitle">Verified by</dt>
                  <dd><strong>{req.bank_user_name || user.name}</strong> ({user.bank_name})</dd>
                </div>

                <div>
                  <dt className="cell-subtitle">Verification timestamp</dt>
                  <dd>{dateLabel(req.bank_verified_at)} {req.bank_verified_at ? new Date(req.bank_verified_at).toLocaleTimeString() : ''}</dd>
                </div>

                {req.bank_remarks && (
                  <div className={`quoted-note ${req.bank_decision === 'verified' ? 'resolved' : ''}`}>
                    <strong>Bank remarks & observations</strong>
                    <p>{req.bank_remarks}</p>
                  </div>
                )}

                <Notice tone="info">
                  <ShieldCheck size={16}/>
                  This verification finding has been submitted to the AICTE officer. The case remains under the authority of the assigned verification officer.
                </Notice>
              </div>
            </Panel>
          ) : (
            <Panel
              title="Record verification decision"
              subtitle="Examine your bank records and record the official decision"
            >
              <form
                className="padded form-stack"
                onSubmit={e => {
                  e.preventDefault()
                  submitDecision.mutate()
                }}
              >
                <div className="field">
                  <label id="verification-action-label">Select verification action</label>
                  <div className="actions stack" role="radiogroup" aria-labelledby="verification-action-label" style={{ marginTop: 8 }}>
                    <label className={`radio-card ${decision === 'verified' ? 'selected' : ''}`}>
                      <input
                        type="radio"
                        name="decision"
                        value="verified"
                        checked={decision === 'verified'}
                        onChange={() => setDecision('verified')}
                      />
                      <div>
                        <strong><CheckCircle2 size={16} className="text-green"/> 1. Verified</strong>
                        <p>FDR details match bank ledger records exactly. Instrument is genuine and active.</p>
                      </div>
                    </label>

                    <label className={`radio-card ${decision === 'rejected' ? 'selected' : ''}`}>
                      <input
                        type="radio"
                        name="decision"
                        value="rejected"
                        checked={decision === 'rejected'}
                        onChange={() => setDecision('rejected')}
                      />
                      <div>
                        <strong><XCircle size={16} className="text-red"/> 2. Rejected</strong>
                        <p>FDR could not be verified, is altered, cancelled, or discrepancies exist.</p>
                      </div>
                    </label>

                    <label className={`radio-card ${decision === 'additional_info_required' ? 'selected' : ''}`}>
                      <input
                        type="radio"
                        name="decision"
                        value="additional_info_required"
                        checked={decision === 'additional_info_required'}
                        onChange={() => setDecision('additional_info_required')}
                      />
                      <div>
                        <strong><CircleAlert size={16} className="text-amber"/> 3. Request Additional Information</strong>
                        <p>Clarification, endorsements, or further documents required before decision.</p>
                      </div>
                    </label>
                  </div>
                </div>

                {decision === 'verified' && (
                  <div className="stack" style={{ marginTop: 12, padding: 12, background: 'var(--bg-subtle, #f8fafc)', borderRadius: 8 }}>
                    <strong>Optional confirmed records:</strong>
                    <div className="form-grid">
                      <label className="field">
                        Confirmed amount (INR)
                        <input
                          type="number"
                          placeholder={String(inst.amount)}
                          value={confirmedAmount}
                          onChange={e => setConfirmedAmount(e.target.value)}
                        />
                      </label>
                      <label className="field">
                        Confirmed maturity date
                        <input
                          type="date"
                          value={confirmedMaturity}
                          onChange={e => setConfirmedMaturity(e.target.value)}
                        />
                      </label>
                    </div>
                  </div>
                )}

                <label className="field" style={{ marginTop: 12 }}>
                  Bank remarks & observations
                  <textarea
                    rows={4}
                    required
                    minLength={decision === 'verified' ? 5 : 10}
                    value={remarks}
                    onChange={e => setRemarks(e.target.value)}
                    placeholder={
                      decision === 'verified'
                        ? 'Confirm instrument details, branch records verification, and any relevant notes (min 5 characters)…'
                        : decision === 'rejected'
                        ? 'Explain why the FDR is rejected (e.g. amount mismatch, unknown reference, account closed; min 10 characters)…'
                        : 'Explain what clarification or additional documents are required from the institution (min 10 characters)…'
                    }
                  />
                  <small>
                    {decision === 'rejected' && 'A clear explanation is required for rejection (min 10 characters).'}
                    {decision === 'additional_info_required' && 'Please describe the missing information clearly (min 10 characters).'}
                    {decision === 'verified' && 'Recorded in the official audit trail for AICTE officers.'}
                  </small>
                </label>

                {submitDecision.error && <ErrorState error={submitDecision.error}/>}

                <div className="form-footer" style={{ marginTop: 16 }}>
                  <span><LockKeyhole size={14}/> Recorded under {user.name} ({user.bank_name})</span>
                  <Button
                    disabled={submitDecision.isPending || (decision !== 'verified' && remarks.trim().length < 10)}
                  >
                    <CheckCircle2 size={16}/>
                    {submitDecision.isPending ? 'Recording decision…' : 'Submit verification decision'}
                  </Button>
                </div>
              </form>
            </Panel>
          )}

          <Panel title="Bank verification standards">
            <div className="padded stack">
              <Notice tone="info">
                <strong>Independent Verification Policy</strong>
                <p>Verifying an FDR confirms its issuance and ledger validity. It does not automatically release funds or authorize regulatory changes.</p>
              </Notice>
              <dl className="detail-list">
                <div>
                  <dt>Bank</dt>
                  <dd>{user.bank_name || 'Assigned bank'}</dd>
                </div>
                <div>
                  <dt>Officer responsible</dt>
                  <dd>{req.requested_by_name || 'AICTE Officer'}</dd>
                </div>
                <div>
                  <dt>Forwarded reference</dt>
                  <dd>{req.id.slice(0, 8)}</dd>
                </div>
              </dl>
            </div>
          </Panel>
        </div>
      </div>

      <Dialog
        open={!!viewer}
        onOpenChange={v => { if (!v) setViewer(null) }}
        title={viewer?.name || 'Document preview'}
        description="Private document preview. If the link expires, close and open it again."
      >
        {viewer && (viewer.mime === 'application/pdf' ? (
          <iframe title="Private document preview" className="document-viewer" src={viewer.url}/>
        ) : (
          <img className="document-image" alt={viewer.name} src={viewer.url}/>
        ))}
      </Dialog>
    </>
  )
}
