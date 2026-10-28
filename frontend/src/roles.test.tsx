import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { SignIn } from './pages/public'
import { ReleaseCard, ReleaseQueue } from './pages/admin'
import { CaseDetail } from './pages/case'
import { api, post, type User } from './lib/api'

let mockCurrentUser: User = {
  id: 'user-institution-1',
  name: 'Ananya Rao',
  email: 'institution@demo.local',
  role: 'institution',
  institution_id: 'inst-1',
  clearance_cell: null,
}

vi.mock('@/App', () => ({
  Brand: () => <span>DepositFlow</span>,
  useUser: () => mockCurrentUser,
}))

vi.mock('./lib/api', async original => {
  const actual = await original<typeof import('./lib/api')>()
  return {
    ...actual,
    post: vi.fn(),
    api: vi.fn(),
  }
})

function mount(node: ReactNode, route = '/') {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/" element={node}/>
          <Route path="/app/deposits/:id" element={node}/>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockCurrentUser = {
    id: 'user-institution-1',
    name: 'Ananya Rao',
    email: 'institution@demo.local',
    role: 'institution',
    institution_id: 'inst-1',
    clearance_cell: null,
  }
})

describe('Role-based workflows and access control', () => {
  describe('Sign In Portals', () => {
    it('auto-fills credentials for Institute and Admin portals', async () => {
      mount(<SignIn/>)
      const user = userEvent.setup()

      expect(screen.getByLabelText('Email address')).toHaveValue('institution@demo.local')
      expect(screen.getByLabelText('Password')).toHaveValue('DemoFlow2026!')

      await user.click(screen.getByRole('button', { name: /Admin/i }))
      expect(screen.getByLabelText('Email address')).toHaveValue('admin@demo.local')
      expect(screen.getByLabelText('Password')).toHaveValue('DemoFlow2026!')
    })
  })

  describe('Release Queue & Clearances across roles', () => {
    const mockRelease = {
      id: 'rel-1',
      deposit_id: 'dep-1',
      reference: 'DF-2026-000001',
      institution_name: 'Meridian Institute of Technology',
      reason: 'Course cycle successfully concluded',
      status: 'under_review',
      created_at: '2026-03-01T10:00:00Z',
      workflow_snapshot: { allow_mock_for_demo: true, cells: ['PGRC', 'Vigilance'] },
      clearances: [
        { id: 'clr-1', cell: 'PGRC', status: 'pending', notes: null },
        { id: 'clr-2', cell: 'Vigilance', status: 'approved', notes: 'No adverse record' },
      ],
      blockers: ['PGRC clearance is pending.'],
      reviewer_ids: ['officer-1'],
      risk: { score: 65, level: 'high' },
    }

    it('hides risk scores from institution role on ReleaseCard', () => {
      mockCurrentUser = {
        id: 'inst-user-1',
        name: 'Ananya Rao',
        email: 'institution@demo.local',
        role: 'institution',
        institution_id: 'inst-1',
        clearance_cell: null,
      }
      mount(<ReleaseCard release={mockRelease}/>)
      expect(screen.queryByText(/65 · High/)).not.toBeInTheDocument()
      expect(screen.queryByText(/High/)).not.toBeInTheDocument()
      expect(screen.getByText('PGRC')).toBeInTheDocument()
      expect(screen.getByText('Authorisation blockers')).toBeInTheDocument()
    })

    it('allows Clearance officer for PGRC to record clearance decision', async () => {
      mockCurrentUser = {
        id: 'pgrc-user-1',
        name: 'Priya Sharma',
        email: 'clearance@demo.local',
        role: 'clearance',
        institution_id: null,
        clearance_cell: 'PGRC',
      }
      mount(<ReleaseCard release={mockRelease}/>)
      // PGRC button is visible
      const recordBtn = screen.getByRole('button', { name: 'Record clearance' })
      expect(recordBtn).toBeInTheDocument()

      const user = userEvent.setup()
      await user.click(recordBtn)
      expect(screen.getByText('PGRC clearance decision')).toBeInTheDocument()
    })

    it('enforces conflict of interest check for Authority role', () => {
      mockCurrentUser = {
        id: 'officer-1', // matches reviewer_ids in mockRelease
        name: 'Dr. Kavita Nair',
        email: 'authority@demo.local',
        role: 'authority',
        institution_id: null,
        clearance_cell: null,
      }
      mount(<ReleaseCard release={mockRelease}/>)
      expect(screen.getByText(/You submitted or reviewed this case. A different authority must record the final decision./)).toBeInTheDocument()
      const decisionBtn = screen.getByRole('button', { name: 'Record final decision' })
      expect(decisionBtn).toBeDisabled()
    })
  })

  describe('Case Workspace Verification Gate & Vigilance Escalation', () => {
    const baseDeposit = {
      id: 'dep-1',
      reference: 'DF-2026-000001',
      institution_id: 'inst-1',
      institution_name: 'Meridian Institute of Technology',
      institution_code: 'DEMO-INST-001',
      programme: 'Engineering and Technology',
      status: 'under_review',
      assigned_officer_id: 'officer-1',
      verified_at: null,
      escalated: true,
      instrument: {
        id: 'inst-1',
        amount: 3500000,
        bank: 'DEMO NATIONAL BANK',
        branch: 'Bhubaneswar',
        number: 'FDR-2026-999',
        depositor_name: 'Meridian Institute of Technology',
        issue_date: '2026-01-01',
        maturity_date: '2031-01-01',
        validity_date: null,
        verification_status: 'officially_confirmed',
      },
      readiness: [
        { key: 'bank', label: 'The bank has confirmed the instrument', met: true, detail: 'Confirmed' },
        { key: 'documents', label: 'The receipt is uploaded and its checks have finished', met: true, detail: 'Uploaded and checked' },
        { key: 'tasks', label: 'Every review task is resolved', met: false, detail: '1 still open.' },
        { key: 'suspicion', label: 'No unresolved suspicion above the limit', met: false, detail: 'Escalated to Vigilance; only Vigilance can clear it.' },
      ],
      documents: [],
      discrepancies: [
        {
          id: 'disc-1',
          code: 'forensic_duplicate',
          severity: 'high',
          status: 'under_review',
          suspicious: true,
          description: 'Document signature matches a different previously pledged instrument.',
          evidence_source: 'forensic_inspection',
          next_step: 'Vigilance evaluation required.',
        }
      ],
      instruments: [{ id: 'inst-1', number: 'FDR-2026-999', amount: 3500000, issue_date: '2026-01-01', maturity_date: '2031-01-01', status: 'active' }],
      verifications: [],
      timeline: [],
      release: null,
      risk: { score: 75, level: 'high' },
      requirement_snapshot: { illustrative: true, explanation: 'Illustrative rule calculation', source_reference: 'APH 2026-27' },
      required_amount: 3500000,
    }

    it('shows red escalation banner and Vigilance review badge; hides officer record resolution on suspicious tasks', async () => {
      mockCurrentUser = {
        id: 'officer-1',
        name: 'Arjun Mehta',
        email: 'officer@demo.local',
        role: 'verification',
        institution_id: null,
        clearance_cell: null,
      }
      vi.mocked(api).mockResolvedValueOnce(baseDeposit)
      mount(<CaseDetail/>, '/app/deposits/dep-1')

      // Case header and summary
      expect(await screen.findByText('DF-2026-000001')).toBeInTheDocument()
      // Red escalation banner
      expect(screen.getByText('Escalated to the Vigilance cell')).toBeInTheDocument()

      // Checklist on overview: unmet items make Mark verification complete disabled
      const completeBtn = screen.getByRole('button', { name: /Mark verification complete/i })
      expect(completeBtn).toBeDisabled()

      // Go to Review tasks tab
      const user = userEvent.setup()
      await user.click(screen.getByRole('tab', { name: /Review tasks/i }))

      // Shows Vigilance review badge
      expect(screen.getByText('Vigilance review')).toBeInTheDocument()
      // Verification officer cannot resolve suspicious task
      expect(screen.queryByRole('button', { name: 'Record resolution' })).not.toBeInTheDocument()
    })

    it('allows Vigilance cell to resolve suspicious finding and see Clear escalation', async () => {
      mockCurrentUser = {
        id: 'vigilance-1',
        name: 'Vikram Sen',
        email: 'vigilance@demo.local',
        role: 'clearance',
        institution_id: null,
        clearance_cell: 'Vigilance',
      }
      vi.mocked(api).mockResolvedValueOnce(baseDeposit)
      mount(<CaseDetail/>, '/app/deposits/dep-1')

      // Vigilance sees Clear escalation button on banner
      expect(await screen.findByRole('button', { name: 'Clear escalation' })).toBeInTheDocument()

      // Go to Review tasks tab
      const user = userEvent.setup()
      await user.click(screen.getByRole('tab', { name: /Review tasks/i }))

      // Vigilance sees Resolve as Vigilance button
      expect(screen.getByRole('button', { name: 'Resolve as Vigilance' })).toBeInTheDocument()
    })

    it('institutions never see escalation banner, risk tab, or readiness checklist', async () => {
      mockCurrentUser = {
        id: 'inst-1',
        name: 'Ananya Rao',
        email: 'institution@demo.local',
        role: 'institution',
        institution_id: 'inst-1',
        clearance_cell: null,
      }
      // Institution payload does not contain readiness, escalated, risk, suspicious
      const instPayload = {
        ...baseDeposit,
        readiness: undefined,
        escalated: false,
        risk: null,
        discrepancies: [
          {
            id: 'disc-1',
            code: 'document_review:disc-1',
            severity: 'warning',
            status: 'under_review',
            description: 'This document requires verification with the issuing bank before review can continue.',
            evidence_source: 'document_review',
            next_step: 'Provide the original instrument or a bank-issued confirmation.',
          }
        ]
      }
      vi.mocked(api).mockResolvedValueOnce(instPayload)
      mount(<CaseDetail/>, '/app/deposits/dep-1')

      expect(await screen.findByText('DF-2026-000001')).toBeInTheDocument()
      // No escalation banner
      expect(screen.queryByText('Escalated to the Vigilance cell')).not.toBeInTheDocument()
      // No verification checklist
      expect(screen.queryByText('Verification checklist')).not.toBeInTheDocument()
      // No Risk tab
      expect(screen.queryByRole('tab', { name: 'Risk' })).not.toBeInTheDocument()
    })
  })
})
