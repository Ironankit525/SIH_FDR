import { test, expect } from '@playwright/test'
import { signIn } from './helpers'

test('switching accounts locks other tabs and reopening uses the current role', async ({ page, context }) => {
  await signIn(page, 'Institution')
  await page.goto('/app/deposits/new')
  await expect(page.getByRole('button', { name: 'Save & continue' })).toBeVisible()
  const other = await context.newPage()
  await signIn(other, 'Admin')
  await expect(page.getByRole('heading', { name: 'Your sign-in changed in another tab' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save & continue' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Reopen workspace' }).click()
  await expect(page.getByLabel('Act as official role')).toHaveValue('admin@demo.local')
  await other.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your sign-in changed in another tab' })).toBeVisible()
  await page.getByRole('button', { name: 'Reopen workspace' }).click()
  await expect(page.getByRole('button', { name: 'Sign in to workspace' })).toBeVisible()
})
