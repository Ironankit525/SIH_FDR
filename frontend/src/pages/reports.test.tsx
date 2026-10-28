import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Reports } from './overview'
import { api } from '@/lib/api'

const viewer = vi.hoisted(() => ({ id: 'admin-1', role: 'admin', name: 'System Admin' }))
vi.mock('@/App', () => ({ useUser: () => viewer }))
vi.mock('@/lib/api', async original => ({
  ...await original<typeof import('@/lib/api')>(),
  api: vi.fn(),
  downloadReport: vi.fn(),
}))

const mockDashboard = {
  total_records: 12,
  total_value: 35000000,
  pending_verification: 2,
  officially_confirmed: 8,
  mock_confirmed: 2,
  discrepancies: 1,
  expiring: 3,
  overdue: 1,
  pending_release: 0,
  completed_approvals: 5,
  renewal_cases: 2,
  status_distribution: [
    { name: 'submitted', value: 3 },
    { name: 'under review', value: 4 },
    { name: 'verified', value: 5 },
  ],
  maturity_distribution: [
    { name: 'Overdue', value: 1 },
    { name: '0–30 days', value: 2 },
    { name: '31–90 days', value: 3 },
    { name: '90+ days', value: 6 },
  ],
  verification_turnaround: [
    { reference: 'DF-2026-000001', hours: 4.5 },
    { reference: 'DF-2026-000002', hours: 8.2 },
  ],
}

function mount() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('Reports & Audit Trail Section - Charts & Animations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api).mockResolvedValue(mockDashboard)
  })

  it('renders Maturity distribution, Case workload and Verification turnaround charts', async () => {
    mount()

    expect(await screen.findByText('Analytics & reports')).toBeInTheDocument()
    expect(screen.getByText('Maturity distribution')).toBeInTheDocument()
    expect(screen.getByText('Case workload')).toBeInTheDocument()
    expect(screen.getByText('Verification turnaround')).toBeInTheDocument()
  })

  it('renders modern pie legend pills with status names and counts', async () => {
    const { container } = mount()

    expect(await screen.findByText('Case workload')).toBeInTheDocument()
    const pieKey = container.querySelector('.modern-pie-key')!
    expect(pieKey).toBeInTheDocument()

    // Legend items and their values within the pie legend
    expect(pieKey).toHaveTextContent('Submitted')
    expect(pieKey).toHaveTextContent('3')
    expect(pieKey).toHaveTextContent('Under Review')
    expect(pieKey).toHaveTextContent('4')
    expect(pieKey).toHaveTextContent('Verified')
    expect(pieKey).toHaveTextContent('5')
  })

  it('wraps charts in scroll reveal containers with animated classes', async () => {
    const { container } = mount()

    await screen.findByText('Maturity distribution')
    const reveals = container.querySelectorAll('.chart-scroll-reveal')
    expect(reveals.length).toBeGreaterThanOrEqual(3)

    // With fallbackInView: true in testing, scroll reveals are in-view
    for (const el of reveals) {
      expect(el).toHaveClass('chart-scroll-reveal')
      expect(el).toHaveClass('is-in-view')
    }
  })
})
