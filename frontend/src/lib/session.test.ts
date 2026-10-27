import { afterEach, expect, it, vi } from 'vitest'
import { api } from './api'
import { SESSION_SIGNAL, TabSession, tabSession } from './session'

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'df_csrf=; Max-Age=0; path=/'
  tabSession.accept()
  localStorage.clear()
})

it('blocks a stale tab after another login, even if no storage event arrives', () => {
  let cookie = 'institution-session'
  const changed = vi.fn()
  const tab = new TabSession(() => cookie, changed)
  expect(tab.check()).toBe('institution-session')
  cookie = 'officer-session'
  expect(() => tab.check()).toThrow('sign-in changed')
  expect(() => tab.check()).toThrow('sign-in changed')
  expect(changed).toHaveBeenCalledTimes(1)
})

it('blocks logout and same-role account changes as well as role changes', () => {
  let cookie = 'first-session'
  const tab = new TabSession(() => cookie, vi.fn())
  cookie = ''
  expect(() => tab.check()).toThrow()
  tab.accept()
  expect(tab.check()).toBe('')
  cookie = 'another-institution'
  expect(() => tab.check()).toThrow()
})

it('does not send an old form under another account', async () => {
  document.cookie = 'df_csrf=institution; path=/'
  tabSession.accept()
  document.cookie = 'df_csrf=officer; path=/'
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  await expect(api('/deposits', { method: 'POST', body: '{}' })).rejects.toThrow('sign-in changed')
  expect(fetch).not.toHaveBeenCalled()
})

it('uses the displayed session CSRF token and discards responses after a session change', async () => {
  document.cookie = 'df_csrf=institution; path=/'
  tabSession.accept()
  vi.stubGlobal('fetch', vi.fn(async (_url, options) => {
    expect(options.headers.get('X-CSRF-Token')).toBe('institution')
    document.cookie = 'df_csrf=officer; path=/'
    return new Response('{}', { status: 200 })
  }))
  await expect(api('/deposits', { method: 'POST', body: '{}' })).rejects.toThrow('sign-in changed')
})

it('accepts an intentional login and signals other tabs without sharing credentials', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => {
    document.cookie = 'df_csrf=new-session-token; path=/'
    return new Response('{"role":"institution"}', { status: 200 })
  }))
  expect(await api('/auth/login', { method: 'POST', body: '{}' })).toEqual({ role: 'institution' })
  expect(tabSession.check()).toBe('new-session-token')
  expect(localStorage.getItem(SESSION_SIGNAL)).toBeTruthy()
  expect(localStorage.getItem(SESSION_SIGNAL)).not.toContain('new-session-token')
})
