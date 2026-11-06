import { beforeEach, expect, test, vi } from 'vitest'

vi.mock('../../services/apiClient', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

import { apiClient } from '../../services/apiClient'
import { assignCandidateToJob, fetchJobCandidates, removeCandidateFromJob } from './api'

const assignment = {
  candidate_id: 'candidate-1',
  full_name: 'Candidate One',
  email: null,
  current_title: 'Developer',
  summary: 'Builds systems.',
  experience_years: 5,
  location: 'Remote',
  skills: [{ name: 'Python', normalized_name: 'python', years_experience: 2 }],
  sources: [],
  stage: 'SOURCED',
}

beforeEach(() => vi.clearAllMocks())

test('lists only the selected job assignments in the selected workspace', async () => {
  vi.mocked(apiClient.get).mockResolvedValueOnce({ data: [assignment] } as never)
  await expect(fetchJobCandidates('workspace-1', 'job-1')).resolves.toMatchObject([{
    candidate_id: 'candidate-1',
    stage: 'SOURCED',
  }])
  expect(apiClient.get).toHaveBeenCalledWith('/jobs/job-1/candidates', {
    params: { workspace_id: 'workspace-1' },
  })
})

test('creates an explicit workspace-scoped job-candidate association', async () => {
  vi.mocked(apiClient.post).mockResolvedValueOnce({ data: assignment } as never)
  await expect(assignCandidateToJob('job-1', {
    workspace_id: 'workspace-1',
    candidate_id: 'candidate-1',
  })).resolves.toMatchObject({ candidate_id: 'candidate-1' })
  expect(apiClient.post).toHaveBeenCalledWith('/jobs/job-1/candidates', {
    workspace_id: 'workspace-1',
    candidate_id: 'candidate-1',
  })
})

test('deletes only the assignment and propagates backend errors', async () => {
  vi.mocked(apiClient.delete).mockResolvedValueOnce({} as never)
  await expect(removeCandidateFromJob('workspace-1', 'job-1', 'candidate-1')).resolves.toBeUndefined()
  expect(apiClient.delete).toHaveBeenCalledWith('/jobs/job-1/candidates/candidate-1', {
    params: { workspace_id: 'workspace-1' },
  })
  const error = new Error('Not Found')
  vi.mocked(apiClient.delete).mockRejectedValueOnce(error)
  await expect(removeCandidateFromJob('workspace-1', 'job-1', 'candidate-1')).rejects.toBe(error)
})
