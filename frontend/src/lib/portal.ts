import type { User } from './api'

// Two doors into the system. Institutions use the Institute portal; every AICTE official uses the Admin portal.
export type Portal = 'institute' | 'admin'
export const portalOf = (role: User['role']): Portal => role === 'institution' ? 'institute' : 'admin'

export const PORTALS: Record<Portal, { name: string; short: string; demoEmail: string; demoLabel: string }> = {
  institute: { name: 'Institute Portal', short: 'Institute', demoEmail: 'institution@demo.local', demoLabel: 'Meridian Institute of Technology' },
  admin: { name: 'AICTE Admin Command', short: 'Admin', demoEmail: 'admin@demo.local', demoLabel: 'Portal administrator' },
}

// The public demo password; the seed lets a deployment choose another.
export const DEMO_PASSWORD = 'DemoFlow2026!'

// Officials are separate accounts, so maker-checker rules (a second officer, a second administrator, Vigilance
// clearing its own escalations) still hold. In a demo the header lets one presenter step between them.
export const OFFICIAL_DEMOS = [
  { email: 'admin@demo.local', label: 'Administrator', note: 'Users, rules, risk policy, imports' },
  { email: 'admin2@demo.local', label: 'Second administrator', note: 'Approves rule and policy changes' },
  { email: 'officer@demo.local', label: 'Verification officer', note: 'Claims cases and verifies' },
  { email: 'officer2@demo.local', label: 'Second verification officer', note: 'Confirms high-severity resolutions' },
  { email: 'clearance@demo.local', label: 'PGRC clearance', note: 'Records PGRC clearance' },
  { email: 'vigilance@demo.local', label: 'Vigilance cell', note: 'Clears escalated cases' },
  { email: 'authority@demo.local', label: 'Approving authority', note: 'Final release decision' },
  { email: 'auditor@demo.local', label: 'Auditor', note: 'Read-only oversight' },
] as const
