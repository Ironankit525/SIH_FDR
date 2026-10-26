import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { RiskPolicy } from './risk-policy'
import { api, post } from '@/lib/api'

const viewer = vi.hoisted(() => ({ id: 'admin-1', role: 'admin' }))
vi.mock('@/App', () => ({ useUser: () => viewer }))
vi.mock('@/lib/api', async original => ({ ...await original<typeof import('@/lib/api')>(), api: vi.fn(), post: vi.fn() }))

const policy = {
  active: { version: 0, weights: { mismatch_amount: 0.5, history_open_high: 0.1 }, category_caps: { behaviour: 0.15 }, thresholds: { medium: 20, high: 50, critical: 80 } },
  engine_version: '1.0.0',
  signals: { mismatch_amount: { category: 'financial', default_weight: 0.5, strength: 1 }, history_open_high: { category: 'behaviour', default_weight: 0.1, strength: 1 } },
  versions: [{ id: 'v1', version: 1, status: 'proposed', weights: { mismatch_amount: 0.7 }, category_caps: { behaviour: 0.15 }, thresholds: { medium: 20, high: 50, critical: 80 },
               notes: 'Amount mismatches deserve more weight', proposed_by: 'admin-1', proposed_by_name: 'Aditi Verma', approved_by_name: null, created_at: '2026-10-25T10:00:00Z' }],
}
const impact = { cases: 3, current: { low: 2, medium: 1, high: 0, critical: 0 }, proposed: { low: 1, medium: 2, high: 0, critical: 0 }, changed: 1,
                 changes: [{ deposit_id: 'd1', reference: 'DF-2026-000001', institution: 'Meridian', from_score: 14, from_level: 'low', to_score: 24, to_level: 'medium' }] }

function mount() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><MemoryRouter><RiskPolicy/></MemoryRouter></QueryClientProvider>)
}

beforeEach(() => { vi.clearAllMocks(); viewer.role = 'admin'; vi.mocked(api).mockResolvedValue(policy); vi.mocked(post).mockResolvedValue(impact) })

describe('risk policy', () => {
  it('gives auditors a read-only view', async () => {
    viewer.role = 'auditor'
    mount()
    expect(await screen.findByText('Mismatch Amount')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /propose changes/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument()
    expect(screen.getByText('Mismatch Amount: 0.5 → 0.7')).toBeInTheDocument()
  })

  it('blocks an invalid draft and previews the full policy it would submit', async () => {
    mount(); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /propose changes/i }))
    const weight = screen.getByLabelText('Weight for Mismatch Amount')
    await user.clear(weight); await user.type(weight, '1.2')
    expect(screen.getByRole('alert')).toHaveTextContent('between 0 and 0.95')
    expect(screen.getByRole('button', { name: /submit for approval/i })).toBeDisabled()
    await user.clear(weight); await user.type(weight, '0.6')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Preview impact' }))
    expect(post).toHaveBeenCalledWith('/admin/risk-weights/preview', { weights: { mismatch_amount: 0.6, history_open_high: 0.1 }, category_caps: { behaviour: 0.15 }, thresholds: { medium: 20, high: 50, critical: 80 } })
    const preview = await screen.findByText('Impact of your draft')
    expect(within(preview.closest('section')!).getByText('1 of 3 cases would change level.')).toBeInTheDocument()
  })

  it('does not let the proposer approve their own version, but lets anyone preview it', async () => {
    mount(); const user = userEvent.setup()
    expect(await screen.findByRole('button', { name: /requires a different administrator/i })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Preview impact of version 1' }))
    expect(post).toHaveBeenCalledWith('/admin/risk-weights/preview', { weights: { mismatch_amount: 0.7 }, category_caps: { behaviour: 0.15 }, thresholds: { medium: 20, high: 50, critical: 80 } })
    expect(await screen.findByText('Impact of version 1')).toBeInTheDocument()
  })
})
