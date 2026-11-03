import { beforeEach, vi } from 'vitest'
import { waitFor } from '@testing-library/react'

const { selectWorkspace, signOut } = vi.hoisted(() => ({ selectWorkspace: vi.fn(), signOut: vi.fn() }))
vi.mock('../../features/auth/AuthContext', () => ({
  useAuth: () => ({
    selectedWorkspace: { workspace_id: 'ws-1', name: 'Workspace One', role: 'RECRUITER' },
    workspaces: [
      { workspace_id: 'ws-1', name: 'Workspace One', role: 'RECRUITER' },
      { workspace_id: 'ws-2', name: 'Workspace Two', role: 'ADMIN' },
    ],
    selectWorkspace,
    signOut,
  }),
}))

import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'

beforeEach(() => {
  selectWorkspace.mockReset()
  signOut.mockReset()
})

function renderSidebar() {
  return render(<MemoryRouter><Sidebar /></MemoryRouter>)
}

test('Keeps workspace switching available in expanded and collapsed navigation', async () => {
  const user = userEvent.setup()
  const { container } = renderSidebar()
  const sidebar = container.querySelector('aside')
  expect(sidebar?.className).toContain('w-16 sm:w-56 md:w-72')

  const workspaceSelect = screen.getByRole('combobox', { name: 'Workspace' })
  await user.click(workspaceSelect)
  await user.click(screen.getByRole('option', { name: 'Workspace Two' }))
  expect(selectWorkspace).toHaveBeenCalledWith({ workspace_id: 'ws-2', name: 'Workspace Two', role: 'ADMIN' })

  fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
  expect(sidebar?.className).toContain('w-16')
  expect(screen.getByRole('combobox', { name: 'Workspace' })).toBeTruthy()
  expect(screen.getByRole('combobox', { name: 'Workspace' })).toHaveClass('select-trigger-compact')
  expect(screen.getByRole('link', { name: 'Dashboard' }).getAttribute('title')).toBe('Dashboard')

  fireEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }))
  expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeTruthy()
})

test('Keeps navigation links accessible when labels are visually collapsed', () => {
  const { container } = renderSidebar()
  fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))

  expect(screen.getByRole('link', { name: 'Matching' })).toHaveAttribute('href', '/matching')
  expect(screen.getByRole('link', { name: 'Shortlisted' })).toHaveAttribute('href', '/shortlisted')
  const collapsedLink = screen.getByRole('link', { name: 'Matching' })
  expect(collapsedLink).toHaveAttribute('title', 'Matching')
  expect(collapsedLink).toHaveClass('h-10', 'w-10', 'shrink-0')
  expect(collapsedLink.querySelector('svg')).toHaveAttribute('width', '21')
  expect(collapsedLink.querySelector('svg')).toHaveAttribute('height', '21')
  expect(container.querySelector('nav')).toHaveClass('space-y-1.5')

  fireEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }))
  expect(screen.getByRole('link', { name: 'Matching' }).querySelector('svg')).toHaveAttribute('width', '17')
})

test('Confirms sign out, calls the existing auth action, and navigates to login', async () => {
  signOut.mockResolvedValue(undefined)
  function CurrentPath() {
    return <span>{useLocation().pathname}</span>
  }

  render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route path="/dashboard" element={<Sidebar />} />
        <Route path="/login" element={<CurrentPath />} />
      </Routes>
    </MemoryRouter>,
  )

  fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }))
  expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  expect(signOut).not.toHaveBeenCalled()

  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Sign Out' }))

  await waitFor(() => expect(signOut).toHaveBeenCalledOnce())
  expect(await screen.findByText('/login')).toBeInTheDocument()
})

test('Cancel closes sign-out confirmation without logging out', () => {
  renderSidebar()
  fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }))
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  expect(signOut).not.toHaveBeenCalled()
})
