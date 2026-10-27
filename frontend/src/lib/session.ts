export const SESSION_CHANGED = 'depositflow:session-changed'
export const SESSION_SIGNAL = 'depositflow:session-update'
export const sessionCookie = () => document.cookie.split('; ').find(c => c.startsWith('df_csrf='))?.slice('df_csrf='.length) || ''

// Pin writes to the session this tab displayed. Never read a replacement
// session's CSRF token just before submitting an old account's form.
export class TabSession {
  private token: string
  private changed = false
  constructor(private read: () => string, private onChange: () => void) { this.token = read() }
  check() {
    if (this.changed || this.read() !== this.token) {
      if (!this.changed) { this.changed = true; this.onChange() }
      throw new Error('Your sign-in changed in another tab. Reopen the workspace before continuing.')
    }
    return this.token
  }
  accept() { this.token = this.read(); this.changed = false }
}

export const tabSession = new TabSession(sessionCookie, () => window.dispatchEvent(new Event(SESSION_CHANGED)))
export function announceSession() {
  tabSession.accept()
  // Only an event identifier is shared, never credentials or account data.
  try { localStorage.setItem(SESSION_SIGNAL, crypto.randomUUID()) } catch { /* Focus and request checks still protect this tab. */ }
}
