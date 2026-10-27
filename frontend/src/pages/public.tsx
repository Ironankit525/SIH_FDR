import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight,
  ShieldCheck,
  FileCheck2,
  CalendarClock,
  GitBranch,
  CheckCircle2,
  Building2,
  Landmark,
  ArrowUpRight,
  Sparkles,
  Scale,
  UploadCloud,
  UserCheck,
  AlertCircle,
  Layers,
  ArrowLeft,
  ShieldAlert,
  ScrollText,
} from 'lucide-react'
import { Brand } from '@/App'
import { Button } from '@/components/ui/button'
import { ErrorState, Notice } from '@/components/common'
import { post, type User } from '@/lib/api'
import { DEMO_PASSWORD, PORTALS, portalOf, type Portal } from '@/lib/portal'
import { InfographicBackground } from '@/components/infographic-bg'

function PublicNav() { return <header className="public-nav"><Brand/><nav><Link to="/information">About the portal</Link><span className="environment-label">SIH26265</span><Button asChild><Link to="/signin">Sign in <ArrowUpRight size={16}/></Link></Button></nav></header> }

export function Landing() {
  return (
    <div className="landing-page">
      {/* Upper section strictly bounded by the horizontal divider */}
      <div className="landing-upper-section">
        {/* Sanity-style 3-part infographic animation with blur & segregation */}
        <InfographicBackground />

        {/* Subtle brand header: only top corner logo, no navigation links or duplicate buttons */}
        <header className="landing-header">
          <Brand light />
        </header>

        <div className="landing-main">
          <section className="landing-hero">
            {/* Left Column: Headline, subtext, unified action buttons */}
            <div className="landing-hero-copy">
              <div className="landing-badge">
                <span className="landing-badge-radar">
                  <span className="landing-radar-ping" />
                  <span className="landing-radar-dot" />
                </span>
                <Sparkles size={14} className="landing-badge-sparkle" />
                <span>Smart India Hackathon 2026</span>
              </div>

              <h1 className="landing-headline">
                Every deposit.<br />
                Every decision.<br />
                <span className="landing-headline-gradient">One clear view.</span>
              </h1>

              <p className="landing-subtext">
                A connected workspace for institutional security deposits. From the first submission to final authorization, keep documents, deadlines, and decisions in step.
              </p>

              <div className="landing-actions">
                <Link to="/signin?portal=institute" className="landing-btn-primary">
                  Institute login <ArrowRight size={16} />
                </Link>
                <Link to="/signin?portal=admin" className="landing-btn-secondary">
                  AICTE Admin login
                </Link>
                <Link to="/information" className="landing-btn-secondary">
                  Explore the workflow
                </Link>
              </div>

              <div className="landing-trust-strip">
                <div className="landing-trust-item">
                  <ShieldCheck size={16} className="text-emerald-400" />
                  <span>Role-based access</span>
                </div>
                <span className="landing-trust-dot text-rose-500">•</span>
                <div className="landing-trust-item">
                  <span>Traceable decisions</span>
                </div>
                <span className="landing-trust-dot text-indigo-400">•</span>
                <div className="landing-trust-item">
                  <span>Private documents</span>
                </div>
              </div>
            </div>

            {/* Right Column: Interactive 3D Sunset Blaze Card */}
            <div className="landing-hero-visual">
              <div className="parent variant-blaze">
                <div className="card" tabIndex={0} role="article" aria-label="DepositFlow 3D Status Card">
                  <div className="logo" aria-hidden="true">
                    <span className="circle circle1" />
                    <span className="circle circle2" />
                    <span className="circle circle3" />
                    <span className="circle circle4" />
                    <span className="circle circle5">
                      <span className="status-text">In Review</span>
                    </span>
                  </div>

                  <div className="glass" />

                  <div className="content">
                    <span className="text">
                      <div style={{ fontSize: '13px', marginBottom: '2px' }}>Security deposit</div>
                      <div style={{ fontSize: '26px', fontWeight: 800, marginBottom: '4px', color: '#7b1113' }}>
                        ₹35,00,000
                      </div>
                      <div style={{ fontSize: '11px', opacity: 0.85, lineHeight: 1.4 }}>
                        Meridian Institute of Technology &middot; Fictional record
                      </div>
                    </span>

                    <div className="bullets-container">
                      <div className="bullet-item">
                        <div className="bullet-dot" aria-hidden="true" />
                        <div className="bullet-content">
                          <div className="bullet-title">Institution submission</div>
                          <div className="bullet-desc">Receipt and supporting records received</div>
                        </div>
                      </div>

                      <div className="bullet-item">
                        <div className="bullet-dot" aria-hidden="true" />
                        <div className="bullet-content">
                          <div className="bullet-title">Document extraction</div>
                          <div className="bullet-desc">Fields extracted; originals preserved</div>
                        </div>
                      </div>

                      <div className="bullet-item">
                        <div className="bullet-dot" aria-hidden="true" />
                        <div className="bullet-content">
                          <div className="bullet-title">Bank evidence review</div>
                          <div className="bullet-desc">Confirmation and discrepancies reviewed</div>
                        </div>
                      </div>

                      <div className="bullet-item">
                        <div className="bullet-dot" aria-hidden="true" />
                        <div className="bullet-content">
                          <div className="bullet-title">Authorised release</div>
                          <div className="bullet-desc">Required clearances and approval</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="bottom">
                    <Link to="/information" className="view-more">
                      <span className="view-more-button">View more</span>
                      <svg
                        className="svg"
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="m6 9 6 6 6-6" />
                      </svg>
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>

      {/* Horizontal divider: strictly divides upper section and lower section */}
      <div className="landing-divider-bar" aria-hidden="true" />

      {/* Lower section: stats strip & footer disclaimer */}
      <div className="landing-lower-section">
        {/* Sanity-style customer proof & metrics strip */}
        <section className="landing-stats-strip">
          <Link to="/information" className="landing-stat-col group">
            <div className="landing-stat-logo logo-loveholidays">
              <svg className="sun-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="3.5" />
                <path d="M12 2.5v2.5M12 19V21.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" />
              </svg>
              <span className="brand-name">loveholidays</span>
            </div>
            <div className="landing-stat-row">
              <span className="landing-stat-number">-97%</span>
              <div className="landing-stat-matrix" aria-hidden="true" />
            </div>
            <div className="landing-stat-caption">
              TRANSLATION COST WITH AI. <span className="landing-stat-link">READ MORE <span className="arrow">→</span></span>
            </div>
          </Link>

          <Link to="/information" className="landing-stat-col group">
            <div className="landing-stat-logo logo-tecovas">
              <span className="brand-name">TECOVAS</span>
            </div>
            <div className="landing-stat-row">
              <span className="landing-stat-number">5X</span>
              <div className="landing-stat-matrix" aria-hidden="true" />
            </div>
            <div className="landing-stat-caption">
              FASTER DEVELOPER VELOCITY. <span className="landing-stat-link">READ MORE <span className="arrow">→</span></span>
            </div>
          </Link>

          <Link to="/information" className="landing-stat-col group">
            <div className="landing-stat-logo logo-complex">
              <span className="brand-name">COMPLEX</span>
            </div>
            <div className="landing-stat-row">
              <span className="landing-stat-number">80h</span>
              <div className="landing-stat-matrix" aria-hidden="true" />
            </div>
            <div className="landing-stat-caption">
              EDITORIAL TIME SAVED PER MONTH. <span className="landing-stat-link">READ MORE <span className="arrow">→</span></span>
            </div>
          </Link>
        </section>

        {/* Dark subtle disclaimer */}
        <footer className="landing-disclaimer">
          SIH26265 prototype · Built for the AICTE problem statement. This is not an official AICTE service. All demonstration institutions and bank records are fictional.
        </footer>
      </div>
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
  const steps = [
    {
      num: '01',
      title: 'Establish the requirement',
      description:
        'An institution selects its programme. The versioned rule engine automatically calculates the configured amount, applies exemptions, and flags conditions requiring manual regulatory review.',
      icon: Scale,
      tags: ['Versioned rule engine', 'Dynamic amount calculation', 'Exemption verification']
    },
    {
      num: '02',
      title: 'Submit and preserve evidence',
      description:
        'Create a draft case, upload the FDR or bank receipt, inspect automated OCR extracted fields, and record reasoned corrections. Original documents and extraction results remain permanently preserved in immutable storage.',
      icon: UploadCloud,
      tags: ['Tamper-proof storage', 'Automated OCR extraction', 'Audited corrections']
    },
    {
      num: '03',
      title: 'Officer verification and evaluation',
      description:
        'A verification officer claims the submission, compares supporting evidence against instrument records, records findings, and evaluates algorithmic risk scoring. Discrepancies require reasoned review before progression.',
      icon: UserCheck,
      tags: ['Verification queue', 'Risk evaluation', 'Discrepancy review']
    },
    {
      num: '04',
      title: 'Vigilance escalations',
      description:
        'When suspicious signals or discrepancy limits are breached, cases automatically escalate to the dedicated Vigilance cell. Normal review halts until Vigilance evaluates findings and clears the escalation.',
      icon: ShieldAlert,
      tags: ['Suspicion threshold gating', 'Vigilance review', 'Formal clearance']
    },
    {
      num: '05',
      title: 'Admin configuration and audit trail',
      description:
        'Administrators manage versioned rule configurations, workflow parameters, and user permissions. Independent auditors inspect the append-only event ledger with cryptographic record verification.',
      icon: ScrollText,
      tags: ['Versioned rule engine', 'Immutable audit ledger', 'System administration']
    }
  ]

  const pillars = [
    {
      icon: ShieldCheck,
      title: 'Four Dedicated Role Domains',
      desc: 'Focused separation of concerns strictly isolated between Educational Institutions, Verification Officers, the Vigilance Escalation Cell, and System Administrators/Auditors.'
    },
    {
      icon: FileCheck2,
      title: 'Auditable Evidence Trail',
      desc: 'Every file upload, OCR parse, discrepancy override, and timestamped sign-off is permanently recorded in an append-only audit ledger.'
    },
    {
      icon: GitBranch,
      title: 'Automated Escalation Governance',
      desc: 'Built-in threshold safeguards automatically intercept suspicious submissions and route them directly to the Vigilance cell for reasoned evaluation.'
    }
  ]

  return (
    <div className="info-page">
      {/* Top Header / Nav */}
      <header className="info-header">
        <div className="info-header-inner">
          <Brand light />
          <nav className="info-header-nav">
            <Link to="/" className="info-back-link">
              <ArrowLeft size={16} />
              <span>Back to home</span>
            </Link>
            <span className="landing-badge-radar-inline">
              <span className="landing-radar-dot" />
              <span>SIH26265</span>
            </span>
            <Link to="/signin" className="landing-btn-primary info-nav-btn">
              <span>Sign in</span>
              <ArrowUpRight size={15} />
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero Section with Live Infographic Background */}
      <div className="info-hero-section">
        <InfographicBackground />

        <div className="info-hero-content">
          <div className="landing-badge">
            <span className="landing-badge-radar">
              <span className="landing-radar-ping" />
              <span className="landing-radar-dot" />
            </span>
            <Sparkles size={14} className="landing-badge-sparkle" />
            <span>Smart India Hackathon 2026 · Architectural Guide</span>
          </div>

          <h1 className="info-hero-headline">
            A complete view of<br />
            <span className="landing-headline-gradient">each deposit.</span>
          </h1>

          <p className="info-hero-subtext">
            DepositFlow brings institution submissions, document evidence, and authorised decisions into one traceable, end-to-end regulatory workflow.
          </p>

          <div className="info-notice-card">
            <div className="info-notice-icon">
              <AlertCircle size={20} />
            </div>
            <div className="info-notice-body">
              <strong>Hackathon Prototype Evaluation</strong>
              <p>
                Built for the AICTE problem statement. Seeded rules are illustrative and mock bank responses are explicitly simulated. The platform orchestrates verification and authorizations without processing direct financial fund transfers.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content: Workflow Steps & Architecture */}
      <main className="info-main-content">
        <div className="info-container">
          <div className="info-section-header">
            <div className="info-section-eyebrow">
              <Layers size={15} />
              <span>END-TO-END WORKFLOW</span>
            </div>
            <h2 className="info-section-title">Five steps from submission to authorization</h2>
            <p className="info-section-desc">
              How institutional deposits progress through rule evaluation, evidence capture, bank confirmation, and release clearance.
            </p>
          </div>

          {/* 5 Step Cards */}
          <div className="info-steps-grid">
            {steps.map(step => {
              const Icon = step.icon
              return (
                <div key={step.num} className="info-step-card">
                  <div className="info-step-header">
                    <span className="info-step-num">{step.num}</span>
                    <div className="info-step-icon-wrap">
                      <Icon size={20} />
                    </div>
                  </div>
                  <h3 className="info-step-title">{step.title}</h3>
                  <p className="info-step-text">{step.description}</p>
                  <div className="info-step-tags">
                    {step.tags.map(tag => (
                      <span key={tag} className="info-step-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Three Core Guarantees */}
          <div className="info-pillars-section">
            <div className="info-section-header">
              <div className="info-section-eyebrow">
                <ShieldCheck size={15} />
                <span>ARCHITECTURAL GUARANTEES</span>
              </div>
              <h2 className="info-section-title">Built on verifiable governance</h2>
            </div>

            <div className="info-pillars-grid">
              {pillars.map((pillar, i) => {
                const Icon = pillar.icon
                return (
                  <div key={i} className="info-pillar-card">
                    <div className="info-pillar-icon">
                      <Icon size={22} />
                    </div>
                    <h3 className="info-pillar-title">{pillar.title}</h3>
                    <p className="info-pillar-desc">{pillar.desc}</p>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Bottom Call-To-Action Banner */}
          <div className="info-cta-card">
            <div className="info-cta-glow" aria-hidden="true" />
            <div className="info-cta-content">
              <h2 className="info-cta-title">Ready to explore the workspace?</h2>
              <p className="info-cta-desc">
                Sign in to experience the live prototype with fictional demonstration accounts across all portals and roles.
              </p>
              <div className="info-cta-actions">
                <Link to="/signin?portal=institute" className="landing-btn-primary">
                  <span>Institute portal</span>
                  <ArrowRight size={17} />
                </Link>
                <Link to="/signin?portal=admin" className="landing-btn-secondary">
                  <span>AICTE Admin command</span>
                </Link>
                <Link to="/" className="landing-btn-secondary">
                  <span>Return to portal home</span>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="info-footer">
        <div className="info-footer-inner">
          <div className="landing-trust-strip">
            <div className="landing-trust-item">
              <ShieldCheck size={16} className="text-emerald-400" />
              <span>Role-based access</span>
            </div>
            <span className="landing-trust-dot text-rose-500">•</span>
            <div className="landing-trust-item">
              <span>Traceable decisions</span>
            </div>
            <span className="landing-trust-dot text-indigo-400">•</span>
            <div className="landing-trust-item">
              <span>Private documents</span>
            </div>
          </div>
          <p className="info-footer-disclaimer">
            SIH26265 prototype · Built for the AICTE problem statement. All demonstration institutions and bank records are fictional.
          </p>
        </div>
      </footer>
    </div>
  )
}
