import { beforeEach, expect, test, vi } from 'vitest'

vi.mock('../../services/apiClient', () => ({
  apiClient: { post: vi.fn(), put: vi.fn() },
}))

import { apiClient } from '../../services/apiClient'
import { createCandidate, updateCandidate, uploadCandidateResume } from './api'

const candidateResponse = {
  id: 'candidate-1',
  full_name: 'Candidate One',
  email: 'candidate@example.test',
  current_title: 'Developer',
  summary: 'Builds systems.',
  experience_years: 5,
  location: 'Remote',
  skills: [{ name: 'Python', normalized_name: 'python', years_experience: null }],
  sources: [],
}

const input = {
  full_name: 'Candidate One',
  email: 'candidate@example.test',
  current_title: 'Developer',
  summary: 'Builds systems.',
  experience_years: 5,
  location: 'Remote',
  skills: ['Python'],
  sources: [],
}

beforeEach(() => vi.clearAllMocks())

test('creates a candidate profile with workspace scope and maps the response', async () => {
  vi.mocked(apiClient.post).mockResolvedValueOnce({ data: candidateResponse } as never)
  await expect(createCandidate({ ...input, workspace_id: 'workspace-1' })).resolves.toMatchObject({
    candidate_id: 'candidate-1',
    email: 'candidate@example.test',
  })
  expect(apiClient.post).toHaveBeenCalledWith('/candidates', expect.objectContaining({ workspace_id: 'workspace-1' }))
})

test('updates a reusable candidate profile without a job association', async () => {
  vi.mocked(apiClient.put).mockResolvedValueOnce({ data: candidateResponse } as never)
  await expect(updateCandidate('workspace-1', 'candidate-1', input)).resolves.toMatchObject({
    candidate_id: 'candidate-1',
  })
  expect(apiClient.put).toHaveBeenCalledWith('/candidates/candidate-1', {
    ...input,
    workspace_id: 'workspace-1',
  })
})

test('uploads a file as multipart form data and returns parsed data only for review', async () => {
  const parsed_candidate = { full_name: 'Parsed Candidate', email: 'parsed@example.test' }
  vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { parsed_candidate } } as never)
  const file = new File(['resume'], 'candidate.pdf', { type: 'application/pdf' })
  await expect(uploadCandidateResume('workspace-1', file)).resolves.toEqual({ parsed_candidate })

  const [url, body, config] = vi.mocked(apiClient.post).mock.calls[0]
  expect(url).toBe('/candidates/resume')
  expect(body).toBeInstanceOf(FormData)
  expect((body as FormData).get('workspace_id')).toBe('workspace-1')
  expect((body as FormData).get('file')).toBe(file)
  expect(config).toEqual({ headers: { 'Content-Type': 'multipart/form-data' } })
})

test('surfaces resume API failures without a parsed-data fallback', async () => {
  const error = new Error('Not Found')
  vi.mocked(apiClient.post).mockRejectedValueOnce(error)
  const file = new File(['resume'], 'candidate.pdf', { type: 'application/pdf' })
  await expect(uploadCandidateResume('workspace-1', file)).rejects.toBe(error)
})
