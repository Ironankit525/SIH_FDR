import { expect, type Page } from '@playwright/test'

// Two doors: Institute and Admin. Officials are separate accounts reached from the Admin header, as in the demo.
export const OFFICIALS: Record<string, { email: string; label: string }> = {
  Admin: { email: 'admin@demo.local', label: 'Administrator' }, Verification: { email: 'officer@demo.local', label: 'Verification officer' },
  'Second officer': { email: 'officer2@demo.local', label: 'Second verification officer' }, PGRC: { email: 'clearance@demo.local', label: 'PGRC clearance' },
  Vigilance: { email: 'vigilance@demo.local', label: 'Vigilance cell' }, Authority: { email: 'authority@demo.local', label: 'Approving authority' }, Auditor: { email: 'auditor@demo.local', label: 'Auditor' },
}
export async function signIn(page: Page, role: string) {
  await page.goto(`/signin?portal=${role === 'Institution' ? 'institute' : 'admin'}`)
  await page.getByRole('button', { name: /^Use the demo/ }).click()
  await page.getByRole('button', { name: 'Sign in to workspace' }).click()
  await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible()
  if (role !== 'Institution' && role !== 'Admin') {
    const switcher = page.getByLabel('Act as official role')
    await switcher.selectOption({ label: OFFICIALS[role].label })
    await expect(switcher).toHaveValue(OFFICIALS[role].email)
    await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible()
  }
}
