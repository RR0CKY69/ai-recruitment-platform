import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchWorkspace: vi.fn(),
  fetchWorkspaceMembers: vi.fn(),
  addWorkspaceMember: vi.fn(),
  updateWorkspace: vi.fn(),
  updateWorkspaceMemberRole: vi.fn(),
  removeWorkspaceMember: vi.fn(),
  updateWorkspaceInContext: vi.fn(),
  removeWorkspaceFromContext: vi.fn(),
  user: {
    id: 'user-1',
    email: 'admin@example.test',
    full_name: 'Admin User',
    is_active: true,
  },
  selectedWorkspace: {
    workspace_id: 'workspace-1',
    name: 'Recruiting',
    slug: 'recruiting',
    role: 'ADMIN' as 'ADMIN' | 'RECRUITER',
  },
}))

vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({
    user: mocks.user,
    selectedWorkspace: mocks.selectedWorkspace,
    updateWorkspaceInContext: mocks.updateWorkspaceInContext,
    removeWorkspaceFromContext: mocks.removeWorkspaceFromContext,
  }),
}))

vi.mock('../components/layout/Sidebar', () => ({
  default: () => null,
}))

vi.mock('../features/workspaces/api', () => ({
  fetchWorkspace: mocks.fetchWorkspace,
  fetchWorkspaceMembers: mocks.fetchWorkspaceMembers,
  addWorkspaceMember: mocks.addWorkspaceMember,
  updateWorkspace: mocks.updateWorkspace,
  updateWorkspaceMemberRole: mocks.updateWorkspaceMemberRole,
  removeWorkspaceMember: mocks.removeWorkspaceMember,
}))

import WorkspaceTeamPage from './WorkspaceTeamPage'

const workspace = {
  workspace_id: 'workspace-1',
  name: 'Recruiting',
  slug: 'recruiting',
  role: 'ADMIN' as const,
}

const members = [
  {
    membership_id: 'membership-1',
    user_id: 'user-1',
    full_name: 'Admin User',
    email: 'admin@example.test',
    role: 'ADMIN' as const,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    membership_id: 'membership-2',
    user_id: 'user-2',
    full_name: 'Recruiter Two',
    email: 'recruiter@example.test',
    role: 'RECRUITER' as const,
    created_at: '2026-02-01T00:00:00Z',
  },
]

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <MemoryRouter initialEntries={['/workspace-team']}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/workspace-team" element={<WorkspaceTeamPage />} />
          <Route path="/workspaces" element={<div>Workspace selection page</div>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()

  mocks.selectedWorkspace = {
    workspace_id: 'workspace-1',
    name: 'Recruiting',
    slug: 'recruiting',
    role: 'ADMIN',
  }

  mocks.fetchWorkspace.mockResolvedValue(workspace)
  mocks.fetchWorkspaceMembers.mockResolvedValue(members)
  mocks.addWorkspaceMember.mockResolvedValue({
    membership_id: 'membership-3',
    user_id: 'user-3',
    full_name: 'New Recruiter',
    email: 'new@example.test',
    role: 'RECRUITER',
    created_at: '2026-11-09T00:00:00Z',
  })
  mocks.updateWorkspace.mockResolvedValue({
    ...workspace,
    name: 'New Workspace Name',
    slug: 'new-workspace-name-test',
  })
  mocks.updateWorkspaceMemberRole.mockResolvedValue({
    ...members[1],
    role: 'ADMIN',
  })
  mocks.removeWorkspaceMember.mockResolvedValue({
    message: 'Workspace member removed.',
  })
})

test('displays workspace details and team members', async () => {
  renderPage()

  expect(await screen.findByRole('heading', { name: 'Recruiting' })).toBeInTheDocument()
  expect(screen.getByText('Slug: recruiting')).toBeInTheDocument()
  expect(screen.getByText('Admin User')).toBeInTheDocument()
  expect(screen.getByText('Recruiter Two')).toBeInTheDocument()
  expect(screen.getByText('recruiter@example.test')).toBeInTheDocument()
})

test('admin can update workspace name and synchronizes auth context', async () => {
  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: /edit name/i }))

  fireEvent.change(within(screen.getByRole('dialog')).getByRole('textbox'), {
    target: { value: 'New Workspace Name' },
  })

  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  await waitFor(() => {
    expect(mocks.updateWorkspace).toHaveBeenCalledWith(
      'workspace-1',
      { name: 'New Workspace Name' },
    )
  })

  expect(mocks.updateWorkspaceInContext).toHaveBeenCalledWith({
    ...workspace,
    name: 'New Workspace Name',
    slug: 'new-workspace-name-test',
  })
})

test('admin can add an existing registered member', async () => {
  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: /add member/i }))

  fireEvent.change(screen.getByLabelText(/email address/i), {
    target: { value: 'new@example.test' },
  })

  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Add member' }))

  await waitFor(() => {
    expect(mocks.addWorkspaceMember).toHaveBeenCalledWith('workspace-1', {
      email: 'new@example.test',
      role: 'RECRUITER',
    })
  })
})

test('admin can change a member role', async () => {
  renderPage()

  const user = userEvent.setup()
  const roleSelect = await screen.findByRole('combobox', {
    name: 'Role for Recruiter Two',
  })

  await user.click(roleSelect)
  await user.click(await screen.findByRole('option', { name: 'ADMIN' }))

  await waitFor(() => {
    expect(mocks.updateWorkspaceMemberRole).toHaveBeenCalledWith(
      'workspace-1',
      'user-2',
      { role: 'ADMIN' },
    )
  })
})

test('admin must confirm before removing a member', async () => {
  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: 'Remove Recruiter Two' }))

  const dialog = screen.getByRole('alertdialog')
  expect(dialog).toHaveTextContent('Recruiter Two')
  expect(mocks.removeWorkspaceMember).not.toHaveBeenCalled()

  fireEvent.click(within(dialog).getByRole('button', { name: 'Remove member' }))

  await waitFor(() => {
    expect(mocks.removeWorkspaceMember).toHaveBeenCalledWith(
      'workspace-1',
      'user-2',
    )
  })
})

test('displays the backend last-admin protection error', async () => {
  mocks.removeWorkspaceMember.mockRejectedValue(
    new Error('The last workspace administrator cannot be removed.'),
  )

  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: 'Remove Admin User' }))

  const dialog = screen.getByRole('alertdialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Remove member' }))

  expect(await screen.findByText(
    'The last workspace administrator cannot be removed.',
  )).toBeInTheDocument()

  expect(screen.getByRole('alertdialog')).toBeInTheDocument()
})

test('admin can demote themselves and loses admin controls', async () => {
  mocks.updateWorkspaceMemberRole.mockResolvedValue({
    ...members[0],
    role: 'RECRUITER',
  })
  mocks.fetchWorkspaceMembers.mockResolvedValue([
    ...members,
    {
      membership_id: 'membership-3',
      user_id: 'user-3',
      full_name: 'Second Admin',
      email: 'second-admin@example.test',
      role: 'ADMIN',
      created_at: '2026-03-01T00:00:00Z',
    },
  ])

  mocks.fetchWorkspace
    .mockResolvedValueOnce(workspace)
    .mockResolvedValue({ ...workspace, role: 'RECRUITER' })

  renderPage()

  const user = userEvent.setup()
  const roleSelect = await screen.findByRole('combobox', {
    name: 'Role for Admin User',
  })

  await user.click(roleSelect)
  await user.click(await screen.findByRole('option', { name: 'RECRUITER' }))

  await waitFor(() => {
    expect(mocks.updateWorkspaceMemberRole).toHaveBeenCalledWith(
      'workspace-1',
      'user-1',
      { role: 'RECRUITER' },
    )
    expect(mocks.updateWorkspaceInContext).toHaveBeenCalledWith({
      ...mocks.selectedWorkspace,
      role: 'RECRUITER',
    })
  })

  await waitFor(() => {
    expect(screen.queryByRole('button', { name: /add member/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit name/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: /role for/i })).not.toBeInTheDocument()
  })
})

test('admin can remove themselves and is redirected to workspace selection', async () => {
  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: 'Remove Admin User' }))

  const dialog = screen.getByRole('alertdialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Remove member' }))

  await waitFor(() => {
    expect(mocks.removeWorkspaceMember).toHaveBeenCalledWith(
      'workspace-1',
      'user-1',
    )
    expect(mocks.removeWorkspaceFromContext).toHaveBeenCalledWith('workspace-1')
    expect(screen.getByText('Workspace selection page')).toBeInTheDocument()
  })
})

test('recruiter can view workspace and members but cannot manage them', async () => {
  mocks.selectedWorkspace = {
    ...mocks.selectedWorkspace,
    role: 'RECRUITER',
  }

  mocks.fetchWorkspace.mockResolvedValue({
    ...workspace,
    role: 'RECRUITER',
  })

  renderPage()

  expect(await screen.findByText('Recruiter Two')).toBeInTheDocument()
  expect(screen.getByText('ADMIN')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /add member/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /edit name/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('combobox', { name: /role for/i })).not.toBeInTheDocument()
})
