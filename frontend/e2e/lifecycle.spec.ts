import { test, expect, type Page } from '@playwright/test'
import { signIn } from './helpers'

// One case, start to finish, each stage by a different account. Officials are separate accounts, so the second
// officer, Vigilance and authority checks are the real ones, not bypassed for the demo.
const day = (offset: number) => new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10)

// A one-page PDF with a text layer, so the cascade reads it at its first stage.
function pdf(lines: string[]) {
  const text = lines.map((line, i) => `BT /F1 12 Tf 50 ${740 - i * 22} Td (${line.replace(/[()\\]/g, '')}) Tj ET`).join('\n')
  const objects = ['<</Type/Catalog/Pages 2 0 R>>', '<</Type/Pages/Kids[3 0 R]/Count 1>>',
    '<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>',
    `<</Length ${text.length}>>\nstream\n${text}\nendstream`, '<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>']
  let body = '%PDF-1.4\n'; const offsets: number[] = []
  objects.forEach((object, i) => { offsets.push(body.length); body += `${i + 1} 0 obj\n${object}\nendobj\n` })
  const xref = body.length
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.map(o => `${String(o).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<</Root 1 0 R/Size ${objects.length + 1}>>\nstartxref\n${xref}\n%%EOF`
  return Buffer.from(body, 'latin1')
}
const file = (name: string, lines: string[]) => ({ name, mimeType: 'application/pdf', buffer: pdf(lines) })

async function upload(page: Page, category: string, document: ReturnType<typeof file>) {
  await page.getByRole('tab', { name: /^Documents/ }).click()
  await page.getByLabel('Document category').selectOption(category)
  await page.locator('input[type="file"]').setInputFiles(document)
  await expect(page.getByText(document.name, { exact: true })).toBeVisible()
}
const signOut = (page: Page) => page.getByRole('button', { name: 'Sign out', exact: true }).click()
async function record(page: Page, button: string | RegExp, fill: (dialog: ReturnType<Page['getByRole']>) => Promise<void>) {
  await page.getByRole('button', { name: button }).first().click()
  const dialog = page.getByRole('dialog')
  await fill(dialog)
  await dialog.getByRole('button', { name: 'Save record' }).click()
  await expect(dialog).toBeHidden()
}

test('a deposit goes from submission to recorded completion, each stage by its own account', async ({ page }) => {
  test.setTimeout(180000)
  const number = `LIFE-${Date.now()}`
  const receipt = file(`${number}.pdf`, ['Bank: DEMO NATIONAL BANK', 'Branch: Education Services Branch', `FDR Number: ${number}`,
    'Depositor Name: Meridian Institute of Technology', 'Amount: INR 3500000.00', `Issue Date: ${day(-400)}`, `Maturity Date: ${day(300)}`,
    'Lien Marked in Favour of: AICTE New Delhi'])

  // 1. The institution submits.
  await signIn(page, 'Institution')
  await page.getByRole('link', { name: 'New Deposit & Calculator' }).click()
  await page.getByRole('combobox', { name: 'Programme', exact: true }).selectOption({ label: 'Engineering and Technology · Undergraduate' })
  await page.getByLabel('Bank name', { exact: true }).fill('DEMO NATIONAL BANK')
  await page.getByLabel('Branch', { exact: true }).fill('Education Services Branch')
  await page.getByLabel('Instrument / FDR number', { exact: true }).fill(number)
  await page.getByLabel('Deposit amount (INR)', { exact: true }).fill('3500000')
  await page.getByLabel('Issue date', { exact: true }).fill(day(-400))
  await page.getByLabel('Bank maturity date', { exact: true }).fill(day(300))
  await page.getByLabel('Regulatory security period ends').fill(day(-5))
  await page.getByLabel('Lien / security details').fill('Lien marked in favour of AICTE New Delhi')
  await page.getByRole('button', { name: 'Save & continue' }).click()
  await expect(page.getByRole('heading', { name: /^DF-/ })).toBeVisible()
  const caseUrl = page.url()
  await upload(page, 'instrument', receipt)
  await expect(page.getByText('Completed', { exact: true })).toBeVisible({ timeout: 20000 })
  await page.getByRole('button', { name: 'Submit for review' }).click()
  await expect(page.getByText('Action recorded successfully.')).toBeVisible()
  await signOut(page)

  // 2. A verification officer obtains the bank's confirmation and signs the case off.
  await signIn(page, 'Verification')
  await page.goto(caseUrl)
  await page.getByRole('button', { name: 'Assign to me' }).click()
  // The original receipt opens beside the extracted fields, not in a separate dialog.
  await page.getByRole('tab', { name: 'Evidence comparison' }).click()
  await page.getByRole('button', { name: 'Show original receipt' }).click()
  await expect(page.getByTitle('Original receipt')).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Institution submitted' })).toBeVisible()
  await page.getByRole('tab', { name: 'Case overview' }).click()
  await expect(page.getByRole('heading', { name: 'Verification checklist' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Mark verification complete' })).toBeDisabled()  // the bank has not confirmed yet
  await page.getByRole('tab', { name: 'Bank verification' }).click()
  await record(page, 'Create request', async dialog => { await expect(dialog.getByLabel('Approved verification channel')).toBeVisible() })
  await upload(page, 'bank_confirmation', file('bank-letter.pdf', ['Bank confirmation letter', `We confirm FDR ${number} for INR 3500000.00`, `Maturity ${day(300)}`]))
  await page.getByRole('tab', { name: 'Bank verification' }).click()
  await record(page, 'Record finding', async dialog => {
    await dialog.getByLabel('Authorised source / bank contact').fill('Branch manager, Education Services Branch')
    await dialog.getByLabel('Verification reference').fill('BANK-REF-2026-001')
    await dialog.getByLabel('Observations and supporting evidence').fill('Branch confirmed the deposit by letter.')
    await dialog.getByLabel('Amount the bank confirmed (INR)').fill('3500000')
    await dialog.getByLabel('Maturity date the bank confirmed').fill(day(300))
  })
  await page.getByRole('tab', { name: /^Review tasks/ }).click()
  // Resolve whatever is open; the list refreshes after each save, so stop when no button appears.
  for (let i = 0; i < 10; i++) {
    const found = await page.getByRole('button', { name: 'Record resolution' }).first().click({ timeout: 4000 }).then(() => true, () => false)
    if (!found) break
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Notes / evidence-based explanation').fill('Checked against the original documents; no concern.')
    await dialog.getByRole('button', { name: 'Save record' }).click()
    await expect(dialog).toBeHidden()
  }
  await page.getByRole('tab', { name: 'Case overview' }).click()
  await expect(page.getByRole('button', { name: 'Mark verification complete' })).toBeEnabled()
  await record(page, 'Mark verification complete', async dialog => { await dialog.getByLabel('Notes / evidence-based explanation').fill('All four requirements are met.') })
  await expect(page.getByText('Verified', { exact: true }).first()).toBeVisible()
  await page.screenshot({ path: 'test-results/lifecycle-verified.png', fullPage: true, animations: 'disabled' })
  await signOut(page)

  // 3. The institution requests release with its supporting documents.
  await signIn(page, 'Institution')
  await page.goto(caseUrl)
  for (const category of ['release_request', 'affidavit', 'approval_letter']) await upload(page, category, file(`${category}-${number}.pdf`, [category.replace('_', ' '), number]))
  await page.getByRole('tab', { name: 'Release workflow' }).click()
  await record(page, /Create release request/, async dialog => { await dialog.getByLabel('Eligibility explanation and request').fill('The regulatory period has ended; requesting release.') })
  await signOut(page)

  // 4. PGRC and Vigilance clear, as separate accounts.
  const card = (reference: string) => page.locator('section.panel', { hasText: reference })
  const reference = (await (async () => { await signIn(page, 'PGRC'); await page.goto(caseUrl); return (await page.getByRole('heading', { level: 1 }).textContent())!.trim() })())
  for (const cell of ['PGRC', 'Vigilance']) {
    if (cell === 'Vigilance') await signIn(page, 'Vigilance')
    await page.getByRole('link', { name: 'Release Clearances & Approvals' }).click()
    await card(reference).getByRole('button', { name: 'Record clearance' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Findings and reasons').fill(`${cell} reviewed the case and clears it.`)
    await dialog.getByRole('button', { name: 'Save record' }).click()
    await expect(dialog).toBeHidden()
    await expect(card(reference).getByText(`${cell} reviewed the case and clears it.`)).toBeVisible()
  }

  // 5. The approving authority decides and records the outcome.
  await signIn(page, 'Authority')
  await page.getByRole('link', { name: 'Release Clearances & Approvals' }).click()
  await expect(card(reference).getByText(/All configured prerequisites are complete/)).toBeVisible()
  await card(reference).getByRole('button', { name: 'Record final decision' }).click()
  await page.getByRole('dialog').getByLabel('Findings and reasons').fill('Every prerequisite and clearance is recorded.')
  await page.getByRole('dialog').getByRole('button', { name: 'Save record' }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await card(reference).getByRole('button', { name: 'Record completion' }).click()
  await page.getByRole('dialog').getByLabel('NOC / sanction / completion reference').fill(`NOC-${number}`)
  await page.getByRole('dialog').getByRole('button', { name: 'Save record' }).click()
  await expect(card(reference).getByText(`NOC-${number}`)).toBeVisible()
  await page.screenshot({ path: 'test-results/lifecycle-completed.png', fullPage: true, animations: 'disabled' })
})
