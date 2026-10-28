import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import type { ReactNode } from 'react'
import { BankDashboard, BankQueue, BankVerificationDetail } from './pages/bank'
import { api, post } from './lib/api'

vi.mock('@/App', () => ({
  Brand: () => <span>DepositFlow</span>,
  useUser: () => ({
    id: 'bank-user-1',
    name: 'Vikram Malhotra',
    email: 'bank@demo.local',
    role: 'bank',
    bank_name: 'DEMO NATIONAL BANK',
  })
}))

vi.mock('./lib/api', async original => {
  const actual = await original<typeof import('./lib/api')>()
  return {
    ...actual,
    post: vi.fn(),
    api: vi.fn(),
  }
})

function mount(node: ReactNode, initialEntries = ['/'], path = '/') {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path={path} element={node} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => vi.clearAllMocks())

describe('Bank role interface tests', () => {
  it('renders the Bank Dashboard with summary metrics and quick actions', async () => {
    vi.mocked(api).mockResolvedValueOnce({
      bank_name: 'DEMO NATIONAL BANK',
      total_requests: 5,
      pending_requests: 2,
      under_verification: 1,
      verified: 1,
      rejected: 1,
      additional_info_required: 0,
      recent: [
        {
          id: 'req-1',
          deposit_id: 'dep-1',
          reference: 'DF-2026-000001',
          institution_name: 'Meridian Institute of Technology',
          instrument_number: 'MATCH-001',
          amount: 3500000,
          status: 'sent',
          created_at: '2026-10-26T10:00:00Z',
        }
      ]
    })

    mount(<BankDashboard/>)

    expect(await screen.findByText('Bank Verification Overview')).toBeInTheDocument()
    expect(screen.getByText('Official Bank Verification Gateway · DEMO NATIONAL BANK')).toBeInTheDocument()
    expect(screen.getByText('DF-2026-000001')).toBeInTheDocument()
    expect(screen.getByText('Meridian Institute of Technology')).toBeInTheDocument()
    expect(screen.getByText('MATCH-001')).toBeInTheDocument()
  })

  it('renders the Bank Queue and allows searching/filtering requests', async () => {
    vi.mocked(api).mockResolvedValueOnce([
      {
        id: 'req-1',
        deposit_id: 'dep-1',
        reference: 'DF-2026-000001',
        institution_name: 'Meridian Institute of Technology',
        institution_code: 'DEMO-INST-001',
        instrument_number: 'MATCH-001',
        branch: 'Education Services Branch',
        depositor_name: 'Meridian Institute',
        amount: 3500000,
        maturity_date: '2027-10-26',
        days_to_maturity: 365,
        created_at: '2026-10-26T10:00:00Z',
        requested_by_name: 'Arjun Mehta',
        status: 'sent',
      }
    ])

    mount(<BankQueue/>)

    expect(await screen.findByText('DF-2026-000001')).toBeInTheDocument()
    expect(screen.getByText('Verification Queue')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/search reference, institution/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /review & verify/i })).toBeInTheDocument()
  })

  it('renders FDR details and allows recording verification decision', async () => {
    vi.mocked(api).mockResolvedValue({
      request: {
        id: 'req-1',
        status: 'under_verification',
        created_at: '2026-10-26T10:00:00Z',
        requested_by_name: 'Arjun Mehta',
        officer_notes: 'Please verify FDR details and branch records.',
      },
      deposit: {
        id: 'dep-1',
        reference: 'DF-2026-000001',
        status: 'submitted',
      },
      institution: {
        id: 'inst-1',
        name: 'Meridian Institute of Technology',
        code: 'DEMO-INST-001',
        state: 'Odisha',
        contact_email: 'institution1@demo.local',
        programme: 'Engineering and Technology',
      },
      instrument: {
        id: 'instr-1',
        bank: 'DEMO NATIONAL BANK',
        branch: 'Main Branch',
        number: 'MATCH-001',
        depositor_name: 'Meridian Institute of Technology',
        amount: 3500000,
        issue_date: '2025-10-26',
        maturity_date: '2027-10-26',
        verification_status: 'pending',
      },
      documents: [
        {
          id: 'doc-1',
          filename: 'MATCH-001-instrument.pdf',
          category: 'instrument',
          size: 15420,
          content_type: 'application/pdf',
          created_at: '2026-10-26T10:00:00Z',
        }
      ]
    })

    vi.mocked(post).mockResolvedValueOnce({
      message: 'Verification decision recorded successfully.',
      request: { id: 'req-1', status: 'verified', bank_decision: 'verified' }
    })

    mount(
      <BankVerificationDetail/>,
      ['/app/bank/verifications/req-1'],
      '/app/bank/verifications/:id'
    )

    expect(await screen.findByText('DF-2026-000001')).toBeInTheDocument()
    const matches = await screen.findAllByText('MATCH-001')
    expect(matches.length).toBeGreaterThan(0)
    expect(screen.getByText('Please verify FDR details and branch records.')).toBeInTheDocument()
    expect(screen.getByText('MATCH-001-instrument.pdf')).toBeInTheDocument()

    // Form selection and submission
    const user = userEvent.setup()
    const textarea = screen.getByPlaceholderText(/confirm instrument details/i)
    await user.type(textarea, 'Instrument confirmed genuine and verified against branch records.')

    const submitBtn = screen.getByRole('button', { name: /submit verification decision/i })
    expect(submitBtn).not.toBeDisabled()
    await user.click(submitBtn)

    expect(post).toHaveBeenCalledWith(
      '/bank/verifications/req-1/decision',
      expect.objectContaining({
        decision: 'verified',
        remarks: 'Instrument confirmed genuine and verified against branch records.',
      })
    )
  })
})

