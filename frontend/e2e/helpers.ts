import { test, expect, type Page } from '@playwright/test'

// A full lifecycle changes accounts repeatedly. Respect the real login limiter
// instead of disabling it or making the suite depend on how quickly earlier tests ran.
async function loginAction(page: Page, action: () => Promise<unknown>) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const [response] = await Promise.all([
      page.waitForResponse(response => new URL(response.url()).pathname === '/api/auth/login'
        && response.request().method() === 'POST'),
      action(),
    ])
    if (response.status() !== 429 || attempt === 1) {
      expect(response.status(), 'Demo sign-in must succeed').toBe(200)
      return
    }
    const seconds = Number(response.headers()['retry-after'])
    expect(Number.isFinite(seconds) && seconds >= 0 && seconds <= 120,
      'Login throttling must provide a bounded Retry-After delay').toBe(true)
    const delay = seconds * 1000 + 1000
    test.setTimeout(test.info().timeout + delay + 10000)
    // This wait follows an explicit server throttle, not an arbitrary UI delay.
    await page.waitForTimeout(delay)
  }
}

// Two doors: Institute and Admin. Officials are separate accounts reached from the Admin header, as in the demo.
export const OFFICIALS: Record<string, { email: string; label: string }> = {
  Admin: { email: 'admin@demo.local', label: 'Administrator' }, Verification: { email: 'officer@demo.local', label: 'Verification officer' },
  'Second officer': { email: 'officer2@demo.local', label: 'Second verification officer' }, PGRC: { email: 'clearance@demo.local', label: 'PGRC clearance' },
  Vigilance: { email: 'vigilance@demo.local', label: 'Vigilance cell' }, Authority: { email: 'authority@demo.local', label: 'Approving authority' }, Auditor: { email: 'auditor@demo.local', label: 'Auditor' },
}
export async function signIn(page: Page, role: string) {
  await page.goto(`/signin?portal=${role === 'Institution' ? 'institute' : 'admin'}`)
  await page.getByRole('button', { name: /^Use the demo/ }).click()
  await loginAction(page, () => page.getByRole('button', { name: 'Sign in to workspace' }).click())
  await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible()
  if (role !== 'Institution' && role !== 'Admin') {
    const switcher = page.getByLabel('Act as official role')
    await loginAction(page, () => switcher.selectOption({ label: OFFICIALS[role].label }))
    await expect(switcher).toHaveValue(OFFICIALS[role].email)
    await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible()
  }
}
