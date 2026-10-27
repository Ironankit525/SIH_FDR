import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { UserMenu } from './shell'
import type { User } from '@/lib/api'

const mockUser: User = {
  id: 'usr-1',
  name: 'Aditi Verma',
  email: 'admin@demo.local',
  role: 'admin',
  institution_id: null,
  clearance_cell: 'HQ'
}

function renderUserMenu(user: User = mockUser) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UserMenu user={user} />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('UserMenu component', () => {
  it('renders user chip without direct logout button in topbar', () => {
    renderUserMenu()
    expect(screen.getByText('Aditi Verma')).toBeInTheDocument()
    expect(screen.getByText(/Admin/)).toBeInTheDocument()
    // No logout button in the topbar UserMenu
    expect(screen.queryByRole('button', { name: /sign out/i })).not.toBeInTheDocument()
  })

  it('links directly to /app/settings with no popup menu', () => {
    renderUserMenu()

    const link = screen.getByRole('link', { name: /account settings for aditi verma/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/app/settings')

    // No popup/menu rendered
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
