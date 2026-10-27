import { useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { SESSION_CHANGED, SESSION_SIGNAL, tabSession } from '@/lib/session'
import { Button } from './ui/button'

export function SessionBoundary({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [changed, setChanged] = useState(false)
  useEffect(() => {
    const invalidate = () => {
      setChanged(true)
      void qc.cancelQueries()
      qc.clear()
    }
    const check = () => { try { tabSession.check() } catch { invalidate() } }
    const storage = (event: StorageEvent) => { if (event.key === SESSION_SIGNAL) check() }
    const visible = () => { if (document.visibilityState === 'visible') check() }
    window.addEventListener(SESSION_CHANGED, invalidate)
    window.addEventListener('storage', storage)
    window.addEventListener('focus', check)
    document.addEventListener('visibilitychange', visible)
    check()
    return () => {
      window.removeEventListener(SESSION_CHANGED, invalidate)
      window.removeEventListener('storage', storage)
      window.removeEventListener('focus', check)
      document.removeEventListener('visibilitychange', visible)
    }
  }, [qc])
  if (changed) return <main className="padded" role="alert">
    <h1>Your sign-in changed in another tab</h1>
    <p>This page has been locked to prevent actions under a different account. Unsaved edits have been discarded.</p>
    <p>Use separate browser profiles to test institution and officer accounts at the same time.</p>
    <Button onClick={() => window.location.assign('/app')}>Reopen workspace</Button>
  </main>
  return children
}
