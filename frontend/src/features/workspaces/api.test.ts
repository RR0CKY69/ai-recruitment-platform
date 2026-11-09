import { beforeEach, expect, test, vi } from 'vitest'

vi.mock('../../services/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { apiClient } from '../../services/apiClient'
import {
  fetchWorkspace,
  fetchWorkspaceMembers,
  addWorkspaceMember,
  updateWorkspace,
  updateWorkspaceMemberRole,
  removeWorkspaceMember,
} from './api'

const workspace = {
  workspace_id: 'workspace-1',
  name: 'Engineering',
  slug: 'engineering',
  role: 'ADMIN' as const,
}

const member = {
  membership_id: 'membership-1',
  user_id: 'user-1',
  full_name: 'John Smith',
  email: 'john@example.com',
  role: 'RECRUITER' as const,
  created_at: '2026-11-09T10:00:00Z',
}

beforeEach(() => vi.clearAllMocks())

test('fetches workspace details', async () => {
  vi.mocked(apiClient.get).mockResolvedValueOnce({ data: workspace } as never)

  await expect(fetchWorkspace('workspace-1')).resolves.toEqual(workspace)

  expect(apiClient.get).toHaveBeenCalledWith('/workspaces/workspace-1')
})

test('fetches workspace members', async () => {
  vi.mocked(apiClient.get).mockResolvedValueOnce({ data: [member] } as never)

  await expect(fetchWorkspaceMembers('workspace-1')).resolves.toEqual([member])

  expect(apiClient.get).toHaveBeenCalledWith('/workspaces/workspace-1/members')
})

test('adds an existing workspace member', async () => {
  vi.mocked(apiClient.post).mockResolvedValueOnce({ data: member } as never)

  await expect(addWorkspaceMember('workspace-1', {
    email: 'john@example.com',
    role: 'RECRUITER',
  })).resolves.toEqual(member)

  expect(apiClient.post).toHaveBeenCalledWith(
    '/workspaces/workspace-1/members',
    { email: 'john@example.com', role: 'RECRUITER' },
  )
})

test('updates workspace name', async () => {
  vi.mocked(apiClient.patch).mockResolvedValueOnce({
    data: { ...workspace, name: 'Product Engineering' },
  } as never)

  await expect(updateWorkspace('workspace-1', {
    name: 'Product Engineering',
  })).resolves.toMatchObject({ name: 'Product Engineering' })

  expect(apiClient.patch).toHaveBeenCalledWith(
    '/workspaces/workspace-1',
    { name: 'Product Engineering' },
  )
})

test('updates a workspace member role', async () => {
  vi.mocked(apiClient.patch).mockResolvedValueOnce({
    data: { ...member, role: 'ADMIN' },
  } as never)

  await expect(updateWorkspaceMemberRole('workspace-1', 'user-1', {
    role: 'ADMIN',
  })).resolves.toMatchObject({ role: 'ADMIN' })

  expect(apiClient.patch).toHaveBeenCalledWith(
    '/workspaces/workspace-1/members/user-1',
    { role: 'ADMIN' },
  )
})

test('removes a workspace member', async () => {
  vi.mocked(apiClient.delete).mockResolvedValueOnce({
    data: { message: 'Workspace member removed.' },
  } as never)

  await expect(removeWorkspaceMember('workspace-1', 'user-1')).resolves.toEqual({
    message: 'Workspace member removed.',
  })

  expect(apiClient.delete).toHaveBeenCalledWith(
    '/workspaces/workspace-1/members/user-1',
  )
})

test('propagates API errors instead of treating failed operations as successful', async () => {
  const error = new Error('Forbidden')
  vi.mocked(apiClient.get).mockRejectedValueOnce(error)

  await expect(fetchWorkspace('workspace-1')).rejects.toBe(error)
})
