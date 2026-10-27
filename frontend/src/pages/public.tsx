import { useState, useEffect } from 'react'
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
  Scale,
  UploadCloud,
  UserCheck,
  AlertCircle,
  Layers,
  ArrowLeft,
  ShieldAlert,
  ScrollText,
  LockKeyhole,
} from 'lucide-react'
import { Brand } from '@/App'
import { Button } from '@/components/ui/button'
import { ErrorState, Notice } from '@/components/common'
import { post, type User } from '@/lib/api'
import { DEMO_PASSWORD, PORTALS, portalOf, type Portal } from '@/lib/portal'
import { InfographicBackground } from '@/components/infographic-bg'
import { DashboardSkeleton } from '@/components/dashboard-skeleton'

function PublicNav() { return <header className="public-nav"><Brand/><nav><Link to="/information">About the portal</Link><Button asChild><Link to="/signin">Sign in <ArrowUpRight size={16}/></Link></Button></nav></header> }

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
                      <span className="view-more-button">Workflow</span>
                      <svg
                        className="svg"
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="m9 18 6-6-6-6" />
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
  const [isSigningIn, setIsSigningIn] = useState(false)
  const form = useForm<Login>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: PORTALS[portal].demoEmail, password: DEMO_PASSWORD },
  })

  useEffect(() => {
    form.reset({ email: PORTALS[portal].demoEmail, password: DEMO_PASSWORD })
  }, [portal, form])

  const mutation = useMutation({
    mutationFn: async (data: Login) => {
      setIsSigningIn(true)
      const user = await post<User>('/auth/login', data)
      // Each door admits only its own accounts, so an official never lands in the Institute workspace or the reverse.
      if (portalOf(user.role) !== portal) {
        await post('/auth/logout').catch(() => undefined)
        throw new Error(`This account belongs to the ${PORTALS[portalOf(user.role)].short} portal. Choose ${PORTALS[portalOf(user.role)].short} above and sign in again.`)
      }
      return user
    },
    onSuccess: async user => {
      qc.clear()
      qc.setQueryData(['me'], user)
      // Allow brief moment for smooth skeleton preloader visibility and fade
      await new Promise(r => setTimeout(r, 700))
      navigate('/app')
    },
    onError: () => {
      setIsSigningIn(false)
    },
  })
  const choose = (next: Portal) => {
    setParams({ portal: next }, { replace: true })
    form.reset({ email: PORTALS[next].demoEmail, password: DEMO_PASSWORD })
    mutation.reset()
  }
  const Copy = PORTAL_COPY[portal]

  if (isSigningIn) {
    return (
      <div className="dashboard-skeleton-overlay">
        <DashboardSkeleton portal={portal} />
      </div>
    )
  }

  return (
    <div className="auth-page">
      {/* Left Column: Sanity-inspired infographic animation & story */}
      <aside className="auth-story">
        <InfographicBackground />

        <div className="auth-story-content">
          <header className="auth-story-header">
            <Brand light />
          </header>

          <div className="auth-story-body">

            <h1 className="auth-story-headline">
              Good governance<br />
              starts with<br />
              <span className="landing-headline-gradient">clear records.</span>
            </h1>

            <p className="auth-story-subtext">
              A connected workspace for institutional security deposits. From the first submission to final authorization, keep documents, deadlines, and decisions in step.
            </p>

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

          <footer className="auth-story-footer">
            SIH26265 prototype · Built for the AICTE problem statement. All demonstration institutions and bank records are fictional.
          </footer>
        </div>
      </aside>

      {/* Right Column: Sleek dark sign in workspace */}
      <main className="auth-main">
        <div className="auth-main-grid" aria-hidden="true" />

        <div className="auth-main-wrapper">
          <Link className="auth-back-link" to="/">
            ← Back to portal home
          </Link>

          <div className="auth-form-card">
            <div className="auth-form-header">
              <div className="auth-form-icon">
                <Copy.icon size={22} />
              </div>
              <h1 className="auth-form-title">Welcome to DepositFlow</h1>
              <p className="auth-form-subtitle">Choose your portal, then sign in.</p>
            </div>

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

            <p className="portal-blurb">
              <strong>{PORTALS[portal].name}.</strong> {Copy.blurb}
            </p>

            <form className="form-stack" onSubmit={form.handleSubmit(data => mutation.mutate(data))}>
              <label className="field">
                Email address
                <input
                  autoComplete="username"
                  type="email"
                  placeholder={portal === 'admin' ? 'official@aicte.gov.in' : 'you@institution.edu.in'}
                  {...form.register('email')}
                />
                {form.formState.errors.email && (
                  <small className="field-error">{form.formState.errors.email.message}</small>
                )}
              </label>

              <label className="field">
                Password
                <input
                  autoComplete="current-password"
                  type="password"
                  placeholder="Enter your password"
                  {...form.register('password')}
                />
                {form.formState.errors.password && (
                  <small className="field-error">{form.formState.errors.password.message}</small>
                )}
              </label>

              {mutation.error && <ErrorState error={mutation.error} />}

              <button
                type="submit"
                className="auth-submit-btn"
                disabled={mutation.isPending}
              >
                {mutation.isPending ? 'Signing in…' : 'Sign in to workspace'}
                <ArrowRight size={17} />
              </button>
            </form>


            {portal === 'institute' && (
              <p className="auth-register-note">
                New institution? <Link to="/register">Register an institution</Link>
              </p>
            )}
          </div>

          <footer className="auth-footer">
            <ShieldCheck size={14} className="text-emerald-400" />
            <span>Your access is limited to your authorised role.</span>
          </footer>
        </div>
      </main>
    </div>
  )
}

export function Register() {
  const [success, setSuccess] = useState(false)
  const [registeredData, setRegisteredData] = useState<{ name: string; email: string } | null>(null)
  const mutation = useMutation({
    mutationFn: (data: any) => post('/auth/register', data),
    onSuccess: (_, variables: any) => {
      setRegisteredData({
        name: variables.name,
        email: variables.contact_email
      })
      setSuccess(true)
    }
  })

  return (
    <div className="auth-page">
      {/* Left Column: Showcase story with live Infographic Background */}
      <aside className="auth-story">
        <InfographicBackground />

        <div className="auth-story-content">
          <header className="auth-story-header">
            <Brand light />
          </header>

          <div className="auth-story-body">

            <h1 className="auth-story-headline">
              Empowering<br />
              institutions with<br />
              <span className="landing-headline-gradient">verifiable trust.</span>
            </h1>

            <p className="auth-story-subtext">
              Register a demo institution workspace to submit security deposit instruments, inspect OCR evidence extraction, and track statutory reviews.
            </p>

            <div className="landing-trust-strip">
              <div className="landing-trust-item">
                <ShieldCheck size={16} className="text-emerald-400" />
                <span>Verified records</span>
              </div>
              <span className="landing-trust-dot text-rose-500">•</span>
              <div className="landing-trust-item">
                <span>Automated checks</span>
              </div>
              <span className="landing-trust-dot text-indigo-400">•</span>
              <div className="landing-trust-item">
                <span>Private evidence</span>
              </div>
            </div>
          </div>

          <footer className="auth-story-footer">
            SIH26265 prototype · Built for the AICTE problem statement. All demo institutions are simulated locally for testing.
          </footer>
        </div>
      </aside>

      {/* Right Column: Sleek Registration Form */}
      <main className="auth-main">
        <div className="auth-main-grid" aria-hidden="true" />

        <div className="auth-main-wrapper wide">
          <Link className="auth-back-link" to="/signin">
            ← Back to sign in
          </Link>

          <div className="auth-form-card">
            {success ? (
              <div className="auth-success-card">
                <div className="auth-success-icon">
                  <CheckCircle2 size={32} />
                </div>
                <h2 className="auth-success-title">Institution registered</h2>
                <p className="auth-success-desc">
                  <strong>{registeredData?.name || 'Your demo institution'}</strong> has been created.
                  You can now sign in using your registered administrator credentials (<code>{registeredData?.email}</code>).
                </p>
                <Link to="/signin" className="auth-submit-btn" style={{ textDecoration: 'none' }}>
                  Continue to sign in
                  <ArrowRight size={17} />
                </Link>
              </div>
            ) : (
              <>
                <div className="auth-form-header">
                  <div className="auth-form-icon">
                    <Building2 size={22} />
                  </div>
                  <h1 className="auth-form-title">Register demo institution</h1>
                  <p className="auth-form-subtitle">Create an institution workspace for regulatory prototype evaluation.</p>
                </div>

                <div className="auth-notice">
                  <AlertCircle size={18} />
                  <div>
                    <strong>Prototype evaluation workspace:</strong> This self-registration registers a fictional institution for demonstration. Official AICTE onboarding requires statutory approval.
                  </div>
                </div>

                <form
                  className="form-stack"
                  onSubmit={e => {
                    e.preventDefault()
                    const formData = Object.fromEntries(new FormData(e.currentTarget))
                    mutation.mutate({
                      ...formData,
                      approval_year: Number(formData.approval_year)
                    })
                  }}
                >
                  <div className="auth-form-section-title">Institution Details</div>

                  <div className="auth-grid-2">
                    <label className="field">
                      Institution name
                      <input
                        required
                        name="name"
                        type="text"
                        placeholder="e.g. Apex Institute of Technology"
                      />
                    </label>

                    <label className="field">
                      Approval year
                      <input
                        required
                        name="approval_year"
                        type="number"
                        defaultValue={new Date().getFullYear()}
                        min={1950}
                        max={2100}
                      />
                    </label>
                  </div>

                  <div className="auth-grid-2">
                    <label className="field">
                      State / UT
                      <input
                        required
                        name="state"
                        type="text"
                        placeholder="e.g. Maharashtra"
                      />
                    </label>

                    <label className="field">
                      Campus address
                      <input
                        required
                        name="address"
                        type="text"
                        placeholder="City, District, PIN code"
                      />
                    </label>
                  </div>

                  <div className="auth-grid-2">
                    <label className="field">
                      Ownership type
                      <select name="ownership" defaultValue="private">
                        <option value="private">Private</option>
                        <option value="government">Government</option>
                        <option value="government_aided">Government aided</option>
                      </select>
                    </label>

                    <label className="field">
                      Land arrangement
                      <select name="land_arrangement" defaultValue="owned">
                        <option value="owned">Owned</option>
                        <option value="private_lease">Private lease</option>
                      </select>
                    </label>
                  </div>

                  <div className="auth-form-section-title">Academic Programme</div>

                  <div className="auth-grid-2">
                    <label className="field">
                      Initial programme
                      <select name="programme" defaultValue="Engineering and Technology">
                        <option value="Engineering and Technology">Engineering and Technology</option>
                        <option value="Management">Management</option>
                        <option value="Computer Applications">Computer Applications</option>
                      </select>
                    </label>

                    <label className="field">
                      Programme level
                      <select name="level" defaultValue="undergraduate">
                        <option value="undergraduate">Undergraduate</option>
                        <option value="postgraduate">Postgraduate</option>
                        <option value="diploma">Diploma</option>
                      </select>
                    </label>
                  </div>

                  <div className="auth-form-section-title">Administrator Account</div>

                  <div className="auth-grid-2">
                    <label className="field">
                      Administrator name
                      <input
                        required
                        name="administrator_name"
                        type="text"
                        placeholder="Dr. Full Name"
                      />
                    </label>

                    <label className="field">
                      Contact email
                      <input
                        required
                        name="contact_email"
                        type="email"
                        placeholder="admin@institution.edu.in"
                      />
                    </label>
                  </div>

                  <label className="field">
                    Account password
                    <input
                      required
                      name="password"
                      type="password"
                      minLength={12}
                      placeholder="At least 12 characters"
                    />
                    <small style={{ color: '#64748b', fontSize: '0.75rem', marginTop: '2px' }}>
                      Must be at least 12 characters long.
                    </small>
                  </label>

                  {mutation.error && <ErrorState error={mutation.error} />}

                  <button
                    type="submit"
                    className="auth-submit-btn"
                    disabled={mutation.isPending}
                  >
                    {mutation.isPending ? 'Creating demo institution…' : 'Create demo institution'}
                    <ArrowRight size={17} />
                  </button>
                </form>

                <p className="auth-register-note">
                  Already have an account? <Link to="/signin">Sign in to workspace</Link>
                </p>
              </>
            )}
          </div>

          <footer className="auth-footer">
            <ShieldCheck size={14} className="text-emerald-400" />
            <span>Prototype environment · Demo data stored locally</span>
          </footer>
        </div>
      </main>
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
