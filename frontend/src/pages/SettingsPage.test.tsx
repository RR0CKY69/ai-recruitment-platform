import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  signOut: vi.fn(),
  user: { id: 'user-1', email: 'recruiter@example.test', full_name: 'Recruiter One', is_active: true },
  selectedWorkspace: {
    workspace_id: 'workspace-1',
    name: 'Recruiting',
    slug: 'recruiting',
    role: 'RECRUITER',
  },
}))

vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({
    user: mocks.user,
    selectedWorkspace: mocks.selectedWorkspace,
    signOut: mocks.signOut,
  }),
}))
vi.mock('../components/layout/Sidebar', () => ({ default: () => null }))

import SettingsPage from './SettingsPage'

function renderSettings() {
  const root = document.createElement('div')
  root.id = 'root'
  document.body.appendChild(root)
  return render(
    <MemoryRouter initialEntries={['/settings']}>
      <Routes>
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/login" element={<h1>Login page</h1>} />
      </Routes>
    </MemoryRouter>,
    { container: root },
  )
}

beforeEach(() => {
  document.querySelectorAll('#root').forEach(root => root.remove())
  vi.clearAllMocks()
  window.localStorage.clear()
  mocks.signOut.mockResolvedValue(undefined)
  mocks.user = { id: 'user-1', email: 'recruiter@example.test', full_name: 'Recruiter One', is_active: true }
  mocks.selectedWorkspace = {
    workspace_id: 'workspace-1',
    name: 'Recruiting',
    slug: 'recruiting',
    role: 'RECRUITER',
  }
})

test('shows only current account and selected workspace data without unsupported edit controls', () => {
  renderSettings()

  expect(screen.getByText('Recruiter One')).toBeInTheDocument()
  expect(screen.getAllByText('recruiter@example.test')).toHaveLength(2)
  expect(screen.getByText('Recruiting')).toBeInTheDocument()
  expect(screen.getByText('RECRUITER')).toBeInTheDocument()
  expect(screen.getByText(/Profile changes are unavailable/)).toBeInTheDocument()
  expect(screen.getByText(/Manage your workspace name and team membership/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument()
  expect(screen.getByText('Access token storage')).toBeInTheDocument()
  expect(screen.queryByText(/Bearer|refresh token/i)).not.toBeInTheDocument()
})

test('persists the clearly browser-local preference and reports storage errors', async () => {
  const { unmount } = renderSettings()
  const checkbox = screen.getByRole('checkbox', { name: /Compact table rows/ })
  fireEvent.click(checkbox)
  expect(window.localStorage.getItem('apex-recruit.preferences.compact-tables')).toBe('true')
  await waitFor(() => expect(document.getElementById('root')).toHaveAttribute('data-compact-tables', 'true'))
  unmount()

  renderSettings()
  expect(screen.getByRole('checkbox', { name: /Compact table rows/ })).toBeChecked()
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('Storage unavailable')
  })
  fireEvent.click(screen.getByRole('checkbox', { name: /Compact table rows/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not save this browser preference.')
})

test('confirms before using the existing secure sign-out and navigates to login', async () => {
  renderSettings()

  fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }))
  expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  expect(mocks.signOut).not.toHaveBeenCalled()
  const dialog = screen.getByRole('alertdialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }))
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Sign Out' }))
  await waitFor(() => expect(mocks.signOut).toHaveBeenCalledOnce())
  expect(await screen.findByRole('heading', { name: 'Login page' })).toBeInTheDocument()
})

test('shows workspace role and account info without exposing admin edit actions', () => {
  mocks.selectedWorkspace = { ...mocks.selectedWorkspace, role: 'ADMIN' }
  renderSettings()
  expect(screen.getByText('ADMIN')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /edit workspace|save/i })).not.toBeInTheDocument()
})
