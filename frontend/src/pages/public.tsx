import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, ShieldCheck, FileCheck2, CalendarClock, GitBranch, CheckCircle2, Building2, Landmark, ArrowUpRight } from 'lucide-react'
import { Brand } from '@/App'
import { Button } from '@/components/ui/button'
import { ErrorState, Notice } from '@/components/common'
import { post, type User } from '@/lib/api'
import { DEMO_PASSWORD, PORTALS, portalOf, type Portal } from '@/lib/portal'

function PublicNav() { return <header className="public-nav"><Brand/><nav><Link to="/information">About the portal</Link><span className="environment-label">SIH26265</span><Button asChild><Link to="/signin">Sign in <ArrowUpRight size={16}/></Link></Button></nav></header> }

export function Landing() {
  return (
    <div className="public-page">
      <PublicNav/>
      <main>
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow"><span className="status-dot"/> Smart India Hackathon 2026</div>
            <h1>Every deposit.<br/>Every decision.<br/><em>One clear view.</em></h1>
            <p>A connected workspace for institutional security deposits. From the first submission to final authorisation, keep documents, deadlines and decisions in step.</p>
            <div className="actions">
              <Button asChild><Link to="/signin?portal=institute">Institute login <ArrowRight size={18}/></Link></Button>
              <Button asChild variant="outline"><Link to="/signin?portal=admin">AICTE Admin login</Link></Button>
              <Link className="text-link" to="/information">Explore the workflow</Link>
            </div>
            <div className="hero-trust">
              <ShieldCheck size={17}/> Role-based access <span>·</span> Traceable decisions <span>·</span> Private documents
            </div>
          </div>
          <div className="hero-visual">
            <div className="hero-orbit"/>
            <div className="preview-window">
              <div className="preview-top">
                <span className="brand-mark"><Building2 size={18}/></span>
                <strong>Deposit workspace</strong>
                <span className="badge green"><i/>In review</span>
              </div>
              <div className="preview-amount">
                <span>Security deposit</span>
                <strong>₹35,00,000</strong>
                <small>Meridian Institute of Technology · Fictional record</small>
              </div>
              <div className="preview-timeline">
                {['Institution submission', 'Document extraction', 'Bank evidence review', 'Authorised release'].map((text, i) => (
                  <div key={text}>
                    <span className={i < 2 ? 'done' : ''}>{i < 2 ? <CheckCircle2 size={17}/> : i + 1}</span>
                    <div>
                      <strong>{text}</strong>
                      <small>{['Receipt and supporting records received', 'Fields extracted; originals preserved', 'Confirmation and discrepancies reviewed', 'Required clearances and approval'][i]}</small>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="floating-note">
              <CalendarClock size={24}/>
              <div>
                <strong>Stay ahead of deadlines</strong>
                <span>Maturity, renewal and release tracked separately</span>
              </div>
            </div>
          </div>
        </section>
        <section className="feature-strip">
          {[
            [FileCheck2, 'Evidence you can follow', 'Keep declarations, extracted fields and independent confirmations distinct.'],
            [CalendarClock, 'Deadlines you can act on', 'See upcoming dates, pending actions and who is responsible.'],
            [GitBranch, 'Decisions you can account for', 'Follow each clearance and authorisation through a complete case history.']
          ].map(([Icon, title, text]) => {
            const I = Icon as typeof FileCheck2
            return (
              <article key={String(title)}>
                <I size={25}/>
                <h2>{String(title)}</h2>
                <p>{String(text)}</p>
              </article>
            )
          })}
        </section>
        <div className="public-disclaimer">
          SIH26265 prototype · Built for the AICTE problem statement. This is not an official AICTE service. All demonstration institutions and bank records are fictional.
        </div>
      </main>
    </div>
  )
}

const loginSchema = z.object({ email: z.string().email('Enter a valid email address'), password: z.string().min(1, 'Enter your password') })
type Login = z.infer<typeof loginSchema>
const PORTAL_COPY: Record<Portal, { icon: typeof Building2; blurb: string }> = {
  institute: { icon: Building2, blurb: 'Submit deposits, answer queries, renew instruments and request release.' },
  admin: { icon: Landmark, blurb: 'Verify evidence, clear escalations, record clearances and run the rules.' },
}

export function SignIn() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const portal: Portal = params.get('portal') === 'admin' ? 'admin' : 'institute'
  const form = useForm<Login>({ resolver: zodResolver(loginSchema), defaultValues: { email: '', password: '' } })
  const mutation = useMutation({
    mutationFn: async (data: Login) => {
      const user = await post<User>('/auth/login', data)
      // Each door admits only its own accounts, so an official never lands in the Institute workspace or the reverse.
      if (portalOf(user.role) !== portal) {
        await post('/auth/logout').catch(() => undefined)
        throw new Error(`This account belongs to the ${PORTALS[portalOf(user.role)].short} portal. Choose ${PORTALS[portalOf(user.role)].short} above and sign in again.`)
      }
      return user
    },
    onSuccess: user => { qc.clear(); qc.setQueryData(['me'], user); navigate('/app') },
  })
  const choose = (next: Portal) => { setParams({ portal: next }, { replace: true }); form.reset({ email: '', password: '' }); mutation.reset() }
  const Copy = PORTAL_COPY[portal]
  return (
    <div className="auth-page">
      <aside className="auth-story">
        <Brand light/>
        <div>
          <div className="eyebrow">A clearer path to compliance</div>
          <h1>Good governance<br/>starts with<br/><em>clear records.</em></h1>
          <p>One place to manage security deposits, verify supporting evidence and move decisions forward.</p>
          <div className="auth-proof"><ShieldCheck/><span>Purpose-built for accountable<br/>institutional workflows.</span></div>
        </div>
        <small>SIH26265 · Smart Automation · Hackathon prototype</small>
      </aside>
      <main className="auth-main">
        <Link className="back-link" to="/">← Back to portal home</Link>
        <div className="auth-form">
          <div className="auth-icon"><Copy.icon size={27}/></div>
          <h1>Welcome to DepositFlow</h1>
          <p>Choose your portal, then sign in.</p>
          <div className="portal-toggle" role="group" aria-label="Portal">
            {(Object.keys(PORTALS) as Portal[]).map(key => (
              <button
                key={key}
                type="button"
                aria-label={`${PORTALS[key].short} portal`}
                aria-pressed={portal === key}
                className={portal === key ? 'active' : ''}
                onClick={() => choose(key)}
              >
                {PORTALS[key].short}
              </button>
            ))}
          </div>
          <p className="portal-blurb"><strong>{PORTALS[portal].name}.</strong> {Copy.blurb}</p>
          <form className="form-stack" onSubmit={form.handleSubmit(data => mutation.mutate(data))}>
            <label className="field">
              Email address
              <input autoComplete="username" type="email" placeholder={portal === 'admin' ? 'official@aicte.gov.in' : 'you@institution.edu.in'} {...form.register('email')}/>
              {form.formState.errors.email && <small className="field-error">{form.formState.errors.email.message}</small>}
            </label>
            <label className="field">
              Password
              <input autoComplete="current-password" type="password" placeholder="Enter your password" {...form.register('password')}/>
              {form.formState.errors.password && <small className="field-error">{form.formState.errors.password.message}</small>}
            </label>
            {mutation.error && <ErrorState error={mutation.error}/>}
            <Button disabled={mutation.isPending}>{mutation.isPending ? 'Signing in…' : 'Sign in to workspace'}<ArrowRight size={17}/></Button>
          </form>
          <div className="demo-login">
            <strong>Explore the fictional demo</strong>
            <p>{portal === 'admin' ? 'Signs in as the portal administrator; the header then lets you act as any other official.' : `Signs in as ${PORTALS.institute.demoLabel}.`}</p>
            <Button type="button" variant="outline" onClick={() => { form.setValue('email', PORTALS[portal].demoEmail); form.setValue('password', DEMO_PASSWORD) }}>
              Use the demo {PORTALS[portal].short.toLowerCase()} account
            </Button>
            <div className="demo-roles">
              {[
                ['institution', 'Institution'],
                ['officer', 'Verification'],
                ['clearance', 'Clearance: PGRC'],
                ['vigilance', 'Clearance: Vigilance'],
                ['authority', 'Authority'],
                ['admin', 'Admin'],
                ['auditor', 'Auditor'],
                ['bank', 'Bank Officer']
              ].map(([email, title]) => (
                <button
                  key={email}
                  type="button"
                  onClick={() => {
                    const targetPortal: Portal = email === 'institution' ? 'institute' : 'admin'
                    if (portal !== targetPortal) {
                      choose(targetPortal)
                    }
                    form.setValue('email', `${email}@demo.local`)
                    form.setValue('password', 'DemoFlow2026!')
                  }}
                >
                  {title}
                </button>
              ))}
            </div>
            <small>Local demo credentials only. If the seed password was changed, enter your configured password.</small>
          </div>
          {portal === 'institute' && <p className="auth-register">New institution? <Link to="/register">Register an institution</Link></p>}
        </div>
        <footer><ShieldCheck size={14}/> Your access is limited to your authorised role.</footer>
      </main>
    </div>
  )
}

export function Register() {
  const [success, setSuccess] = useState(false)
  const mutation = useMutation({ mutationFn: (data: any) => post('/auth/register', data), onSuccess: () => setSuccess(true) })
  return (
    <div className="public-page">
      <PublicNav/>
      <div className="narrow-page">
        <h1>Register a demo institution</h1>
        <Notice>This creates a fictional institution for prototype evaluation. Official onboarding requires AICTE authorisation.</Notice>
        {success ? (
          <div className="success-panel">
            <CheckCircle2/>
            <h2>Institution created</h2>
            <Button asChild><Link to="/signin">Continue to sign in</Link></Button>
          </div>
        ) : (
          <form className="panel form-stack padded" onSubmit={e => { e.preventDefault(); const data = Object.fromEntries(new FormData(e.currentTarget)); mutation.mutate({ ...data, approval_year: Number(data.approval_year) }) }}>
            {[
              ['name', 'Institution name'],
              ['administrator_name', 'Administrator name'],
              ['contact_email', 'Email address', 'email'],
              ['state', 'State'],
              ['address', 'Address'],
              ['approval_year', 'Approval year', 'number'],
              ['password', 'Password (at least 12 characters)', 'password']
            ].map(([name, title, type]) => (
              <label className="field" key={name}>
                {title}
                <input required name={name} type={type || 'text'} minLength={name === 'password' ? 12 : undefined} defaultValue={name === 'approval_year' ? new Date().getFullYear() : undefined}/>
              </label>
            ))}
            <label className="field">Ownership<select name="ownership"><option value="private">Private</option><option value="government">Government</option><option value="government_aided">Government aided</option></select></label>
            <label className="field">Land arrangement<select name="land_arrangement"><option value="owned">Owned</option><option value="private_lease">Private lease</option></select></label>
            <label className="field">Programme<select name="programme"><option>Engineering and Technology</option><option>Management</option><option>Computer Applications</option></select></label>
            <label className="field">Level<select name="level"><option value="undergraduate">Undergraduate</option><option value="postgraduate">Postgraduate</option><option value="diploma">Diploma</option></select></label>
            {mutation.error && <ErrorState error={mutation.error}/>}
            <Button disabled={mutation.isPending}>Create demo institution</Button>
          </form>
        )}
      </div>
    </div>
  )
}

export function Information() {
  return (
    <div className="public-page">
      <PublicNav/>
      <main className="narrow-page">
        <div className="eyebrow">Portal guide</div>
        <h1>A complete view of each deposit</h1>
        <p className="lead">DepositFlow brings institution submissions, document evidence and authorised decisions into one traceable workflow.</p>
        <Notice>This is a hackathon prototype, not an official government portal. Seeded rules are illustrative and mock bank responses are explicitly simulated.</Notice>
        {[
          ['1. Establish the requirement', 'An institution selects its programme. The versioned rule engine explains the configured amount, exemptions and any need for manual review.'],
          ['2. Submit and preserve evidence', 'Create a draft, upload a receipt, inspect extracted fields and record corrections. Original documents and extraction results remain available.'],
          ['3. Review and verify', 'A verification officer claims the case, compares the evidence and records simulated bank results or authorised manual confirmation. Automated discrepancies require reasoned review.'],
          ['4. Monitor and renew', 'Track bank maturity, regulatory security periods and renewal action dates separately. A replacement links to the previous instrument and its documents.'],
          ['5. Request and authorise release', 'Submit supporting records and obtain every configured clearance. The approving authority records the decision and completion reference. The portal never transfers money.']
        ].map(([title, text]) => (
          <section className="guide-step" key={title}>
            <h2>{title}</h2>
            <p>{text}</p>
          </section>
        ))}
        <Button asChild><Link to="/signin">Open your workspace <ArrowRight size={16}/></Link></Button>
      </main>
    </div>
  )
}
