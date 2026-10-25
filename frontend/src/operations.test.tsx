import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { RuleEditor } from './components/rule-editor'
import { ImportRecords } from './pages/import-records'
import { AuditPage } from './pages/overview'
import { api, post } from './lib/api'

vi.mock('@/App', () => ({ useUser: () => ({ id: 'admin-1', role: 'admin' }) }))
vi.mock('./lib/api', async original => ({ ...await original<typeof import('./lib/api')>(), api: vi.fn(), post: vi.fn() }))
function mount(node: ReactNode) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>)
}
beforeEach(() => vi.clearAllMocks())

const rule = { rule_id: 'rule-1', title: 'Illustrative requirements', version: 1, effective_from: '2024-01-01', effective_to: '2027-12-31', illustrative: true,
  source_reference: 'Illustrative examples for testing', config: { amounts: { 'Engineering and Technology|undergraduate': 3500000 }, exempt_ownership: ['government'], private_lease_multiplier: 2 } }

describe('rule editor', () => {
  it('blocks duplicate programmes and submits the full configuration', async () => {
    vi.mocked(post).mockResolvedValue({}); const done = vi.fn()
    mount(<RuleEditor base={rule} onDone={done}/>); const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /add programme/i }))
    const names = screen.getAllByLabelText('Programme')
    await user.type(names[1], 'Engineering and Technology')
    expect(screen.getByRole('alert')).toHaveTextContent('only once')
    expect(screen.getByRole('button', { name: /submit for approval/i })).toBeDisabled()
    await user.selectOptions(screen.getAllByLabelText('Level')[1], 'diploma')
    await user.type(screen.getAllByLabelText('Amount')[1], '1500000')
    await user.click(screen.getByLabelText('Private'))
    await user.click(screen.getByRole('button', { name: /submit for approval/i }))
    await waitFor(() => expect(done).toHaveBeenCalled())
    expect(post).toHaveBeenCalledWith('/admin/rules', expect.objectContaining({ rule_id: 'rule-1', config: {
      amounts: { 'Engineering and Technology|undergraduate': 3500000, 'Engineering and Technology|diploma': 1500000 },
      exempt_ownership: ['government', 'private'], private_lease_multiplier: 2 } }))
  })
})

describe('record import', () => {
  it('checks the file first and imports only after confirmation', async () => {
    const results = [{ row: 2, institution_code: 'DEMO-INST-001', number: 'LEG-1', status: 'ready', errors: [] },
                     { row: 3, institution_code: 'NOPE', number: 'LEG-2', status: 'error', errors: ["Unknown institution code 'NOPE'"] }]
    vi.mocked(api).mockResolvedValueOnce({ rows: 2, ready: 1, errors: 1, committed: false, results })
      .mockResolvedValueOnce({ rows: 2, ready: 1, errors: 1, committed: true, results: [{ ...results[0], status: 'imported', reference: 'DF-2026-ABC123' }, results[1]] })
    mount(<ImportRecords/>); const user = userEvent.setup()
    await user.upload(screen.getByLabelText('Choose CSV'), new File(['institution_code\n'], 'legacy.csv', { type: 'text/csv' }))
    await user.click(screen.getByRole('button', { name: 'Check file' }))
    expect(await screen.findByText("Unknown institution code 'NOPE'")).toBeInTheDocument()
    expect(vi.mocked(api).mock.calls[0][1]!.body).toBeInstanceOf(FormData)
    expect((vi.mocked(api).mock.calls[0][1]!.body as FormData).get('commit')).toBe('false')
    await user.click(screen.getByRole('button', { name: 'Import 1 record' }))
    expect(await screen.findByText(/Imported 1 record/)).toBeInTheDocument()
    expect((vi.mocked(api).mock.calls[1][1]!.body as FormData).get('commit')).toBe('true')
  })
})

describe('audit search', () => {
  it('sends filters to the server and pages through results', async () => {
    const items = Array.from({ length: 50 }, (_, i) => ({ id: `e${i}`, action: 'deposit_submitted', actor_name: 'Ananya Rao', entity_id: 'deposit-123456789012345', created_at: '2026-10-25T10:00:00Z', event_hash: 'a'.repeat(64), before: {}, after: {} }))
    vi.mocked(api).mockResolvedValue({ items, total: 120, limit: 50, offset: 0, actions: ['deposit_submitted', 'risk_assessed'] })
    mount(<AuditPage/>); const user = userEvent.setup()
    expect(await screen.findByText('Showing 1–50 of 120 events')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Record or case reference'), 'DF-2026-000002')
    await user.selectOptions(screen.getByLabelText('Event'), 'risk_assessed')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(vi.mocked(api)).toHaveBeenLastCalledWith('/audit?entity=DF-2026-000002&action=risk_assessed&limit=50&offset=0'))
    await user.click(screen.getByRole('button', { name: /older/i }))
    await waitFor(() => expect(vi.mocked(api)).toHaveBeenLastCalledWith('/audit?entity=DF-2026-000002&action=risk_assessed&limit=50&offset=50'))
  })
})
