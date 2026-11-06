import { beforeEach, expect, test, vi } from 'vitest'

vi.mock('../../services/apiClient', () => ({
  apiClient: { post: vi.fn(), put: vi.fn() },
}))

import { apiClient } from '../../services/apiClient'
import { createJob, updateJob } from './api'

const response = {
  id: 'job-1',
  title: 'Platform Engineer',
  description: 'Build services.',
  required_skills: ['Python'],
  minimum_experience_years: 4,
  employment_type: 'Full-time',
  location: 'Remote',
  status: 'OPEN' as const,
  candidate_count: 2,
}

beforeEach(() => vi.clearAllMocks())

test('creates a workspace-scoped job and maps the backend response', async () => {
  vi.mocked(apiClient.post).mockResolvedValueOnce({ data: response } as never)
  await expect(createJob({
    workspace_id: 'workspace-1',
    title: 'Platform Engineer',
    description: 'Build services.',
    required_skills: ['Python'],
    minimum_experience_years: 4,
    employment_type: 'Full-time',
    location: 'Remote',
    status: 'OPEN',
  })).resolves.toMatchObject({
    job_id: 'job-1',
    title: 'Platform Engineer',
    candidate_count: 2,
  })
  expect(apiClient.post).toHaveBeenCalledWith('/jobs', expect.objectContaining({ workspace_id: 'workspace-1' }))
})

test('updates job fields and status through the workspace-scoped contract', async () => {
  vi.mocked(apiClient.put).mockResolvedValueOnce({ data: { ...response, status: 'ON_HOLD' } } as never)
  await expect(updateJob('workspace-1', 'job-1', {
    title: 'Platform Engineer',
    description: 'Updated.',
    required_skills: ['Python'],
    minimum_experience_years: 4,
    employment_type: 'Full-time',
    location: 'Remote',
    status: 'ON_HOLD',
  })).resolves.toMatchObject({ status: 'ON_HOLD' })
  expect(apiClient.put).toHaveBeenCalledWith('/jobs/job-1', expect.objectContaining({
    workspace_id: 'workspace-1',
    status: 'ON_HOLD',
  }))
})

test('does not convert a missing backend operation into a successful job response', async () => {
  const error = new Error('Not Found')
  vi.mocked(apiClient.post).mockRejectedValueOnce(error)
  await expect(createJob({
    workspace_id: 'workspace-1',
    title: 'Engineer',
    description: 'Build.',
    required_skills: [],
    minimum_experience_years: null,
    employment_type: null,
    location: null,
    status: 'OPEN',
  })).rejects.toBe(error)
})
