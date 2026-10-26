import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { SignIn } from './pages/public'
import { DepositForm } from './pages/case'
import { ActionDialog } from './components/common'
import { post } from './lib/api'

vi.mock('@/App', () => ({ Brand: () => <span>DepositFlow</span>, useUser: () => ({ id: 'owner', role: 'institution', institution_id: 'institution' }) }))
vi.mock('./lib/api', async original => { const actual = await original<typeof import('./lib/api')>(); return { ...actual, post: vi.fn(), api: vi.fn().mockResolvedValue([{ id: 'institution', name: 'Test Institution', programmes: [{ id: 'programme', name: 'Engineering and Technology', level: 'undergraduate' }] }]) } })
function mount(node: ReactNode) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>) }
beforeEach(() => vi.clearAllMocks())

describe('critical interface flows', () => {
  it('shows server authentication failure without navigating or hiding the form', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('Email or password is incorrect'))
    mount(<SignIn/>); const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email address'), 'user@example.org')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: /sign in to workspace/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect')
    expect(screen.getByLabelText('Email address')).toHaveValue('user@example.org')
  })

  it('turns away an official who signs in through the Institute door, and signs them out', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id: 'official', role: 'verification', name: 'Officer' }).mockResolvedValueOnce({})
    mount(<SignIn/>); const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email address'), 'officer@demo.local')
    await user.type(screen.getByLabelText('Password'), 'DemoFlow2026!')
    await user.click(screen.getByRole('button', { name: /sign in to workspace/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('belongs to the Admin portal')
    expect(vi.mocked(post)).toHaveBeenCalledWith('/auth/logout')
  })

  it('offers exactly two portals and fills the matching demo account', async () => {
    mount(<SignIn/>); const user = userEvent.setup()
    expect(within(screen.getByRole('group', { name: 'Portal' })).getAllByRole('button').map(b => b.textContent)).toEqual(['Institute', 'Admin'])
    await user.click(screen.getByRole('button', { name: 'Use the demo institute account' }))
    expect(screen.getByLabelText('Email address')).toHaveValue('institution@demo.local')
    await user.click(screen.getByRole('button', { name: 'Admin' }))
    await user.click(screen.getByRole('button', { name: 'Use the demo admin account' }))
    expect(screen.getByLabelText('Email address')).toHaveValue('admin@demo.local')
  })

  it('blocks a deposit whose bank maturity precedes its issue date', async () => {
    mount(<DepositForm/>); const user = userEvent.setup()
    await screen.findByRole('option', { name: /Engineering and Technology/ })
    await user.selectOptions(screen.getByLabelText('Programme'), 'programme')
    await user.type(screen.getByLabelText('Bank name'), 'Test Bank')
    await user.type(screen.getByLabelText('Branch'), 'Main Branch')
    await user.type(screen.getByLabelText('Instrument / FDR number'), 'TEST-001')
    await user.clear(screen.getByLabelText('Depositor name')); await user.type(screen.getByLabelText('Depositor name'), 'Example Institution')
    await user.type(screen.getByLabelText('Deposit amount (INR)'), '3500000')
    await user.type(screen.getByLabelText('Issue date'), '2026-01-10')
    await user.type(screen.getByLabelText('Bank maturity date'), '2026-01-01')
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(await screen.findByText('Maturity must be after the issue date')).toBeInTheDocument()
    expect(vi.mocked(post).mock.calls.some(call => call[0] === '/deposits')).toBe(false)
  })

  it('keeps a blocked approval open and displays the server clearance requirement', async () => {
    const onClose = vi.fn(); const action = vi.fn().mockRejectedValue(new Error('Vigilance clearance is pending.'))
    mount(<ActionDialog open title="Final release decision" onClose={onClose} fields={[{ name: 'notes', label: 'Decision rationale', type: 'textarea' }]} action={action}/>)
    const user = userEvent.setup(); await user.type(screen.getByLabelText('Decision rationale'), 'I reviewed the submitted evidence')
    await user.click(screen.getByRole('button', { name: 'Save record' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Vigilance clearance is pending.')
    expect(onClose).not.toHaveBeenCalled()
  })
})
