import { Activity, Building, CalendarClock, ChartNoAxesCombined, CircleCheckBig, ClipboardCheck, FilePlus2, Files, Gauge, LayoutDashboard, ShieldAlert, type LucideIcon } from 'lucide-react'
import type { User } from './api'
import { portalOf, type Portal } from './portal'

export interface NavLinkDef { path: string; name: string; icon: LucideIcon; end?: boolean; match?: string[]; exact?: boolean; exclude?: string[] }
export interface NavGroup { title: string; links: NavLinkDef[] }
export interface Tab { path: string; name: string; roles?: User['role'][] }

// Tabs that sit above a page when it belongs to a family of screens, so one sidebar entry can reach all of them.
const TAB_FAMILIES: Record<Portal, Tab[][]> = {
  institute: [
    [{ path: '/app/deposits/new', name: 'New deposit' }, { path: '/app/requirement', name: 'Requirement calculator' }],
    [{ path: '/app/maturity', name: 'Renewals & maturity' }, { path: '/app/releases', name: 'Release requests' }],
  ],
  admin: [
    [{ path: '/app/institutions', name: 'Institutions' }, { path: '/app/deposits', name: 'Deposit registry' }, { path: '/app/maturity', name: 'Maturity & renewals' }],
    [{ path: '/app/reports', name: 'Management reports' }, { path: '/app/audit', name: 'Audit trail' }],
    [{ path: '/app/admin/rules', name: 'Requirement rules', roles: ['admin'] }, { path: '/app/admin/risk', name: 'Risk policy' }, { path: '/app/risk-evaluation', name: 'Risk evaluation' }],
    [{ path: '/app/admin/system', name: 'System monitor' }, { path: '/app/admin/users', name: 'Users & access' }, { path: '/app/admin/workflows', name: 'Workflow settings' }, { path: '/app/admin/alerts', name: 'Alert configuration' }, { path: '/app/admin/import', name: 'Import records' }],
  ],
}

export function navigationFor(user: User): NavGroup[] {
  if (user.role === 'bank') {
    return [{
      title: 'Bank Gateway',
      links: [
        { path: '/app', name: 'Bank Overview', icon: LayoutDashboard, end: true },
        { path: '/app/bank/queue', name: 'Verification Queue', icon: ClipboardCheck },
      ]
    }]
  }
  if (portalOf(user.role) === 'institute') {
    return [{ title: 'Workspace', links: [
      { path: '/app', name: 'Dashboard', icon: LayoutDashboard, end: true },
      { path: '/app/deposits/new', name: 'New Deposit & Calculator', icon: FilePlus2, match: ['/app/deposits/new', '/app/requirement'] },
      { path: '/app/deposits', name: 'My Deposits & FDRs', icon: Files, exclude: ['/app/deposits/new'] },
      { path: '/app/maturity', name: 'Renewals & Releases', icon: CalendarClock, match: ['/app/maturity', '/app/releases'] },
    ] }]
  }
  const governance: NavLinkDef[] = []
  if (user.role === 'admin') governance.push({ path: '/app/admin/rules', name: 'Rules & Risk Policy', icon: Gauge, match: ['/app/admin/rules', '/app/admin/risk', '/app/risk-evaluation'] })
  if (user.role === 'auditor') governance.push({ path: '/app/admin/risk', name: 'Rules & Risk Policy', icon: Gauge, match: ['/app/admin/risk', '/app/risk-evaluation'] })
  if (user.role === 'admin') governance.push({ path: '/app/admin/system', name: 'System Monitor', icon: Activity, match: ['/app/admin/system', '/app/admin/users', '/app/admin/workflows', '/app/admin/alerts', '/app/admin/import'] })
  return [
    { title: 'Operations', links: [
      { path: '/app', name: 'Command Dashboard', icon: LayoutDashboard, end: true },
      { path: '/app/verification', name: 'Verification Queue', icon: ClipboardCheck },
      { path: '/app/escalations', name: 'Vigilance & Escalations', icon: ShieldAlert },
      { path: '/app/releases', name: 'Release Clearances & Approvals', icon: CircleCheckBig },
    ] },
    { title: 'Records', links: [
      { path: '/app/institutions', name: 'Institutions & Registry', icon: Building, match: ['/app/institutions', '/app/deposits', '/app/maturity'], exact: true },
      { path: '/app/reports', name: 'Reports & Audit Trail', icon: ChartNoAxesCombined, match: ['/app/reports', '/app/audit'] },
    ] },
    ...(governance.length ? [{ title: 'Governance', links: governance }] : []),
  ]
}

export function linkActive(link: NavLinkDef, pathname: string) {
  if (link.exclude?.some(ex => pathname === ex || pathname.startsWith(ex + '/'))) return false
  const paths = link.match ?? [link.path]
  if (link.end || link.exact) return paths.includes(pathname)
  return paths.some(path => pathname === path || pathname.startsWith(path + '/'))
}

export function tabsFor(user: User, pathname: string): Tab[] {
  const family = TAB_FAMILIES[portalOf(user.role)].find(tabs => tabs.some(tab => tab.path === pathname))
  return family ? family.filter(tab => !tab.roles || tab.roles.includes(user.role)) : []
}
