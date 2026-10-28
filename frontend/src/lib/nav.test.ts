import { describe, it, expect } from 'vitest'
import type { User } from './api'
import { linkActive, navigationFor, tabsFor } from './nav'

const as = (role: User['role'], clearance_cell: string | null = null) => ({ id: role, name: role, email: `${role}@demo.local`, role, institution_id: null, clearance_cell }) as User
const names = (user: User) => navigationFor(user).flatMap(group => group.links.map(link => link.name))

describe('portal navigation', () => {
  it('gives institutions only the Institute workspace', () => {
    expect(names(as('institution'))).toEqual(['Dashboard', 'New Deposit & Calculator', 'My Deposits & FDRs', 'Renewals & Releases'])
  })

  it('gives every official the command centre, and governance only to those who may use it', () => {
    for (const role of ['verification', 'clearance', 'authority', 'auditor'] as const) {
      expect(names(as(role))).toEqual(expect.arrayContaining(['Command Dashboard', 'Verification Queue', 'Vigilance & Escalations', 'Release Clearances & Approvals', 'Institutions & Registry', 'Reports & Audit Trail']))
    }
    expect(names(as('admin'))).toEqual(expect.arrayContaining(['Rules & Risk Policy', 'System Monitor']))
    expect(names(as('verification'))).not.toContain('System Monitor')
    expect(names(as('auditor'))).toContain('Rules & Risk Policy')
    expect(names(as('auditor'))).not.toContain('System Monitor')
  })

  it('keeps one sidebar entry active for every screen in its family', () => {
    const admin = navigationFor(as('admin')).flatMap(group => group.links)
    const system = admin.find(link => link.name === 'System Monitor')!
    expect(['/app/admin/system', '/app/admin/users', '/app/admin/import'].every(path => linkActive(system, path))).toBe(true)
    expect(linkActive(admin.find(link => link.name === 'Command Dashboard')!, '/app/deposits')).toBe(false)
  })

  it('shows tabs only for screens that belong to a family, and hides rules from non-administrators', () => {
    expect(tabsFor(as('admin'), '/app/admin/rules').map(tab => tab.name)).toEqual(['Requirement rules', 'Risk policy', 'Risk evaluation'])
    expect(tabsFor(as('auditor'), '/app/admin/risk').map(tab => tab.name)).toEqual(['Risk policy', 'Risk evaluation'])
    expect(tabsFor(as('institution'), '/app/releases').map(tab => tab.name)).toEqual(['Renewals & maturity', 'Release requests'])
    expect(tabsFor(as('institution'), '/app')).toEqual([])
  })

  it('distinguishes New Deposit & Calculator from My Deposits & FDRs without mutual highlight', () => {
    const institute = navigationFor(as('institution')).flatMap(group => group.links)
    const newDeposit = institute.find(link => link.name === 'New Deposit & Calculator')!
    const myDeposits = institute.find(link => link.name === 'My Deposits & FDRs')!

    expect(linkActive(newDeposit, '/app/deposits/new')).toBe(true)
    expect(linkActive(myDeposits, '/app/deposits/new')).toBe(false)

    expect(linkActive(newDeposit, '/app/deposits')).toBe(false)
    expect(linkActive(myDeposits, '/app/deposits')).toBe(true)

    expect(linkActive(newDeposit, '/app/requirement')).toBe(true)
    expect(linkActive(myDeposits, '/app/requirement')).toBe(false)

    expect(linkActive(newDeposit, '/app/deposits/DEP-001')).toBe(false)
    expect(linkActive(myDeposits, '/app/deposits/DEP-001')).toBe(true)
  })
})
