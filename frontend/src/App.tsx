import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { Routes, Route, Navigate, Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Building2, ArrowRight, ShieldCheck, Settings, X } from 'lucide-react'
import { api, type User } from './lib/api'
import { navigationFor, linkActive } from './lib/nav'
import { PORTALS, portalOf } from './lib/portal'
import { label } from './lib/utils'
import { Loading } from './components/common'
import { useDrawerGesture } from './components/motion'
import { GlobalSearch, MenuButton, NotificationDrawer, PortalBadge, RoleSwitcher, SectionTabs, ThemeSwitcher, UserMenu } from './components/shell'
import { Landing, SignIn, Register, Information } from './pages/public'
import { Dashboard, Deposits, Institutions, Requirement, Notifications, SettingsPage, Reports, AuditPage } from './pages/overview'
import { DepositForm, CaseDetail } from './pages/case'
import { ReleaseQueue, AdminPage } from './pages/admin'
import { RiskPolicy } from './pages/risk-policy'
import { ImportRecords } from './pages/import-records'
import { RiskEvaluation } from './pages/risk-evaluation'

const UserContext = createContext<User | null>(null)
export const useUser = () => useContext(UserContext)!
export function Brand({ light = false }: { light?: boolean }) { return <Link to="/" className={`brand ${light ? 'brand-light' : ''}`}><span className="brand-mark"><Building2 size={23}/></span><span>Deposit<span className="brand-flow">Flow</span><small>AICTE · Regulation Bureau</small></span></Link> }

// Breadcrumb names for pages that are not in the navigation menu.
const PAGE_TITLES: Record<string, string> = { '/app/settings': 'Account settings', '/app/notifications': 'Notifications', '/app/deposits': 'Deposits', '/app/requirement': 'Requirement calculator', '/app/risk-evaluation': 'Evaluation results' }

function Shell() {
  const userQuery = useQuery<User>({ queryKey: ['me'], queryFn: () => api('/auth/me'), retry: false })
  const location = useLocation(); const [mobile, setMobile] = useState(false); const [logoutError, setLogoutError] = useState(''); const [scrolled, setScrolled] = useState(false)
  const drawerRef = useRef<HTMLElement>(null); const scrimRef = useRef<HTMLDivElement>(null)
  useDrawerGesture(drawerRef, scrimRef, mobile, setMobile, !!userQuery.data)
  // The top bar's soft edge shows only once content is underneath it.
  useEffect(() => { const onScroll = () => setScrolled(window.scrollY > 4); onScroll(); window.addEventListener('scroll', onScroll, { passive: true }); return () => window.removeEventListener('scroll', onScroll) }, [])
  if (userQuery.isPending) return <Loading/>
  if (!userQuery.data) return <Navigate to="/signin" replace/>
  const user = userQuery.data; const portal = portalOf(user.role)
  const navigation = navigationFor(user); const links = navigation.flatMap(group => group.links)
  const active = links.find(link => linkActive(link, location.pathname))
  const current = active?.name ?? PAGE_TITLES[location.pathname] ?? 'Case workspace'
  return <UserContext.Provider value={user}><div className="app-shell" data-portal={portal}><div ref={scrimRef} className={`mobile-scrim ${mobile ? 'visible' : ''}`} onClick={() => setMobile(false)}/>
    <aside ref={drawerRef} className={`sidebar ${mobile ? 'is-open' : ''}`}>
      <div className="sidebar-brand"><Brand/><button className="icon-button mobile-only" aria-label="Close navigation" onClick={() => setMobile(false)}><X/></button></div>
      <div className="workspace-card"><span className="workspace-icon"><Building2 size={19}/></span><div><strong>{PORTALS[portal].name}</strong><small>{portal === 'admin' ? `${label(user.role)}${user.clearance_cell ? ` · ${user.clearance_cell}` : ''}` : user.name}</small></div></div>
      <nav>{navigation.map(group => <div className="nav-group" key={group.title}><div className="nav-label">{group.title}</div>{group.links.map(link => <NavLink to={link.path} end={link.end ?? false} key={link.path} onClick={() => setMobile(false)} className={`nav-link ${link === active ? 'active' : ''}`}><link.icon size={18}/>{link.name}</NavLink>)}</div>)}</nav>
      <div className="sidebar-bottom"><div className="help-card"><ShieldCheck size={22}/><strong>Every action, accounted for.</strong><p>Secure records. Clear responsibilities. Complete histories.</p><Link to="/information">Portal guide <ArrowRight size={14}/></Link></div><NavLink to="/app/settings" className="nav-link"><Settings size={18}/>Settings</NavLink><div className="sidebar-footer"><span className="status-dot"/> SIH 2026 · Prototype v1.0</div></div>
    </aside>
    <div className="main-shell"><header className={`topbar${scrolled ? ' is-scrolled' : ''}`}>
      <div className="breadcrumb"><MenuButton onOpen={() => setMobile(true)}/><PortalBadge user={user}/><span>/</span><strong>{current}</strong></div>
      <GlobalSearch/>
      <div className="topbar-actions"><RoleSwitcher user={user}/><ThemeSwitcher/><NotificationDrawer/><div className="topbar-divider"/><UserMenu user={user} onError={setLogoutError}/></div>
    </header>
    <main className="page-content">{logoutError && <div role="alert" className="notice error">{logoutError}</div>}<SectionTabs user={user}/><Outlet/></main>
    <footer className="page-footer"><span>DepositFlow · Security Deposit & FDR Management</span><span><ShieldCheck size={13}/> Fictional demo · No financial transactions</span></footer></div></div></UserContext.Provider>
}

export default function App() { return <Routes><Route path="/" element={<Landing/>}/><Route path="/information" element={<Information/>}/><Route path="/signin" element={<SignIn/>}/><Route path="/register" element={<Register/>}/><Route path="/app" element={<Shell/>}><Route index element={<Dashboard/>}/><Route path="deposits" element={<Deposits/>}/><Route path="deposits/new" element={<DepositForm/>}/><Route path="deposits/:id" element={<CaseDetail/>}/><Route path="verification" element={<Deposits mode="verification"/>}/><Route path="escalations" element={<Deposits mode="escalations"/>}/><Route path="maturity" element={<Deposits mode="maturity"/>}/><Route path="releases" element={<ReleaseQueue/>}/><Route path="institutions" element={<Institutions/>}/><Route path="requirement" element={<Requirement/>}/><Route path="notifications" element={<Notifications/>}/><Route path="settings" element={<SettingsPage/>}/><Route path="reports" element={<Reports/>}/><Route path="audit" element={<AuditPage/>}/><Route path="admin/risk" element={<RiskPolicy/>}/><Route path="admin/import" element={<ImportRecords/>}/><Route path="risk-evaluation" element={<RiskEvaluation/>}/><Route path="admin/:section" element={<AdminPage/>}/></Route><Route path="*" element={<div className="empty"><h1>Page not found</h1><Link to="/app">Return to your workspace</Link></div>}/></Routes> }
