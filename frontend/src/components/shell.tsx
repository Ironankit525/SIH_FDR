import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Check, LogOut, Menu, Monitor, Moon, Search, Sun, UserCog } from 'lucide-react'
import { api, post, type Row, type User } from '@/lib/api'
import { dateLabel, label } from '@/lib/utils'
import { OFFICIAL_DEMOS, PORTALS, DEMO_PASSWORD, portalOf } from '@/lib/portal'
import { applyTheme, storedTheme, type Theme } from '@/lib/theme'
import { tabsFor } from '@/lib/nav'

export function PortalBadge({ user }: { user: User }) {
  const portal = portalOf(user.role)
  return <span className={`portal-badge ${portal}`}>{PORTALS[portal].name}</span>
}

// Records are the one thing every official and institution looks for, so search goes to the registry.
export function GlobalSearch() {
  const navigate = useNavigate()
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const q = String(new FormData(event.currentTarget).get('q') || '').trim()
    if (q) navigate(`/app/deposits?q=${encodeURIComponent(q)}`)
  }
  return <form className="global-search" role="search" onSubmit={submit}><Search size={16}/><input name="q" aria-label="Search deposits" placeholder="Search reference, institution or FDR number…"/></form>
}

const THEMES: Theme[] = ['system', 'light', 'dark']
export function ThemeSwitcher() {
  const [theme, setTheme] = useState<Theme>(storedTheme())
  const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]
  const Icon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor
  return <button className="icon-button" aria-label={`Theme: ${theme}. Switch to ${next}`} title={`Theme: ${label(theme)}`} onClick={() => { applyTheme(next); setTheme(next) }}><Icon size={18}/></button>
}

export function NotificationDrawer() {
  const [open, setOpen] = useState(false); const qc = useQueryClient(); const ref = useRef<HTMLDivElement>(null)
  const query = useQuery<Row[]>({ queryKey: ['notifications'], queryFn: () => api('/notifications') })
  const read = useMutation({ mutationFn: (path: string) => post(path), onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }) })
  const unread = query.data?.filter(n => !n.read).length ?? 0
  useEffect(() => {
    if (!open) return
    const close = (event: Event) => { if (event instanceof KeyboardEvent ? event.key === 'Escape' : !ref.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('keydown', close); document.addEventListener('pointerdown', close)
    return () => { document.removeEventListener('keydown', close); document.removeEventListener('pointerdown', close) }
  }, [open])
  return <div className="notification-wrap" ref={ref}>
    <button className="notification-button" aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} aria-expanded={open} onClick={() => setOpen(!open)}><Bell size={19}/>{unread > 0 && <i/>}</button>
    {open && <aside className="notification-drawer" role="dialog" aria-label="Notifications">
      <div className="drawer-heading"><strong>Notifications</strong>{unread > 0 && <button className="text-link" onClick={() => read.mutate('/notifications/read-all')}><Check size={14}/>Mark all read</button>}</div>
      {!query.data?.length ? <p className="drawer-empty">You’re up to date.</p> : <ul>{query.data.slice(0, 8).map(n => <li key={n.id} className={n.read ? '' : 'unread'}>
        <div><strong>{n.title}</strong><p>{n.body}</p><small>{dateLabel(n.created_at)}</small></div>
        {!n.read && <button className="icon-button" aria-label="Mark as read" onClick={() => read.mutate(`/notifications/${n.id}/read`)}><Check size={15}/></button>}
      </li>)}</ul>}
      <Link className="drawer-all" to="/app/notifications" onClick={() => setOpen(false)}>View all notifications</Link>
    </aside>}
  </div>
}

// Demo only: officials are separate accounts, so stepping between them keeps every maker-checker rule intact.
export function RoleSwitcher({ user }: { user: User }) {
  const qc = useQueryClient(); const navigate = useNavigate()
  const health = useQuery<Row>({ queryKey: ['health'], queryFn: () => api('/health'), staleTime: Infinity })
  const swap = useMutation({
    mutationFn: (email: string) => post('/auth/login', { email, password: DEMO_PASSWORD }),
    onSuccess: signedIn => { qc.clear(); qc.setQueryData(['me'], signedIn); navigate('/app') },
  })
  if (!health.data?.demo || portalOf(user.role) !== 'admin') return null
  return <label className="role-switch" title="Demo only: sign in as another AICTE official">
    <UserCog size={16}/><span>Acting as</span>
    <select aria-label="Act as official role" value={OFFICIAL_DEMOS.some(d => d.email === user.email) ? user.email : ''} disabled={swap.isPending} onChange={event => swap.mutate(event.target.value)}>
      {OFFICIAL_DEMOS.map(demo => <option key={demo.email} value={demo.email}>{demo.label}</option>)}
    </select>
    {swap.error && <small role="alert" className="field-error">Could not switch: {(swap.error as Error).message}</small>}
  </label>
}

export function UserMenu({ user }: { user: User; onError?: (message: string) => void }) {
  const initials = user.name.split(' ').slice(0, 2).map(part => part[0]).join('')
  return (
    <Link to="/app/settings" className="user-chip" title="Account settings" aria-label={`Account settings for ${user.name}`}>
      <span className="avatar">{initials}</span>
      <span className="user-label">
        <strong>{user.name}</strong>
        <span>{label(user.role)}{user.clearance_cell ? ` · ${user.clearance_cell}` : ''}</span>
      </span>
    </Link>
  )
}

export function MenuButton() {
  return null
}

export function SectionTabs({ user }: { user: User }) {
  const { pathname } = useLocation()
  const tabs = tabsFor(user, pathname)
  if (tabs.length < 2) return null
  return <nav className="section-tabs" aria-label="Section">{tabs.map(tab => <NavLink key={tab.path} to={tab.path} end className={({ isActive }) => isActive ? 'active' : ''}>{tab.name}</NavLink>)}</nav>
}
