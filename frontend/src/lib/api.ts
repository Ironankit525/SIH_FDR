export type Row = Record<string, any>
export interface User { id: string; name: string; email: string; role: 'institution' | 'verification' | 'clearance' | 'authority' | 'admin' | 'auditor' | 'bank' | 'vigilance'; institution_id: string | null; clearance_cell: string | null; bank_name?: string | null }
export class ApiError extends Error {
  blockers?: string[]
  constructor(message: string, public status: number, blockers?: string[]) {
    super(message)
    this.blockers = blockers
  }
}
export function csrf() { return document.cookie.split('; ').find(c => c.startsWith('df_csrf='))?.split('=').slice(1).join('=') || '' }
export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (!(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (options.method && options.method !== 'GET') headers.set('X-CSRF-Token', csrf())
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: 'include' })
  if (!response.ok) {
    const data = await response.json().catch(() => ({})); const detail = data.detail
    const blockers = Array.isArray(detail?.blockers) ? detail.blockers : undefined
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((e: Row) => `${e.loc?.slice(1).join(' ')}: ${e.msg}`).join('; ')
        : detail?.message || (blockers ? blockers.join('. ') : 'The request could not be completed.')
    throw new ApiError(message, response.status, blockers)
  }
  return response.json()
}
export const post = <T = any>(path: string, body: unknown = {}) => api<T>(path, { method: 'POST', body: JSON.stringify(body) })
export async function downloadReport(kind = 'deposits') {
  const response = await fetch(`/api/reports/export?kind=${kind}`, { credentials: 'include' })
  if (!response.ok) throw new Error('Report export failed. Check your permissions.')
  const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href = url; link.download = `depositflow-${kind}.csv`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
