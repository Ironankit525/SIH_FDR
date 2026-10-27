import { announceSession, tabSession } from './session'
export type Row = Record<string, any>
export interface User { id: string; name: string; email: string; role: 'institution' | 'verification' | 'clearance' | 'authority' | 'admin' | 'auditor'; institution_id: string | null; clearance_cell: string | null }
export class ApiError extends Error { constructor(message: string, public status: number) { super(message) } }
export function csrf() { return tabSession.check() }
export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const login = path === '/auth/login' && options.method === 'POST'
  const token = login ? '' : tabSession.check()
  const headers = new Headers(options.headers)
  if (!(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (options.method && options.method !== 'GET') headers.set('X-CSRF-Token', token)
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: 'include' })
  if (response.ok && (login || path === '/auth/logout' && options.method === 'POST')) announceSession()
  else if (!login) tabSession.check()
  if (!response.ok) {
    const data = await response.json().catch(() => ({})); const detail = data.detail
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e: Row) => `${e.loc?.slice(1).join(' ')}: ${e.msg}`).join('; ') : detail?.blockers ? detail.blockers.join(' ') : detail?.message || 'The request could not be completed.'
    throw new ApiError(message, response.status)
  }
  const data = await response.json()
  if (!login) tabSession.check()
  return data
}
export const post = <T = any>(path: string, body: unknown = {}) => api<T>(path, { method: 'POST', body: JSON.stringify(body) })
export async function downloadReport(kind = 'deposits') {
  tabSession.check()
  const response = await fetch(`/api/reports/export?kind=${kind}`, { credentials: 'include' })
  tabSession.check()
  if (!response.ok) throw new Error('Report export failed. Check your permissions.')
  const blob = await response.blob(); tabSession.check()
  const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `depositflow-${kind}.csv`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
