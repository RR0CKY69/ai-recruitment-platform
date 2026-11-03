import { beforeEach, expect, test, vi } from 'vitest'

vi.mock('../../services/apiClient', () => ({
  apiClient: { get: vi.fn() },
}))

import { apiClient } from '../../services/apiClient'
import { fetchCandidate, fetchCandidates, fetchHealth, fetchJobs, fetchMatchScoreDistribution } from './api'

beforeEach(() => {
  vi.clearAllMocks()
})

test('maps backend job IDs to the frontend job shape', async () => {
  vi.mocked(apiClient.get).mockResolvedValueOnce({
    data: [{
      id: 'job-uuid',
      title: 'Engineer',
      description: 'Build services.',
      required_skills: ['Python'],
      minimum_experience_years: 3,
      employment_type: 'Full-time',
      status: 'OPEN',
      location: null,
      candidate_count: 7,
    }],
  } as never)

  await expect(fetchJobs('workspace-uuid')).resolves.toEqual([
    {
      job_id: 'job-uuid',
      title: 'Engineer',
      status: 'OPEN',
      location: undefined,
      description: 'Build services.',
      required_skills: ['Python'],
      minimum_experience_years: 3,
      employment_type: 'Full-time',
      candidate_count: 7,
    },
  ])
  expect(apiClient.get).toHaveBeenCalledWith('/jobs', {
    params: { workspace_id: 'workspace-uuid' },
  })
})

test('maps backend candidate IDs to the frontend candidate shape', async () => {
  vi.mocked(apiClient.get).mockResolvedValueOnce({
    data: [{
      id: 'candidate-uuid',
      full_name: 'Candidate',
      summary: 'Experienced developer.',
      current_title: null,
      location: 'Remote',
      experience_years: 6,
      skills: [{ name: 'Python', normalized_name: 'python', years_experience: 5 }],
      sources: [],
    }],
  } as never)

  await expect(fetchCandidates('workspace-uuid')).resolves.toEqual([
    {
      candidate_id: 'candidate-uuid',
      full_name: 'Candidate',
      current_title: undefined,
      location: 'Remote',
      summary: 'Experienced developer.',
      experience_years: 6,
      skills: [{ name: 'Python', normalized_name: 'python', years_experience: 5 }],
      sources: [],
    },
  ])
  expect(apiClient.get).toHaveBeenCalledWith('/candidates', {
    params: { workspace_id: 'workspace-uuid' },
  })
})

test('reads service health from the existing API health endpoint', async () => {
  vi.mocked(apiClient.get).mockResolvedValueOnce({ data: { status: 'ok' } } as never)

  await expect(fetchHealth()).resolves.toEqual({ status: 'ok' })
  expect(apiClient.get).toHaveBeenCalledWith('/health')
})

test('fetches a candidate detail with the active workspace scope', async () => {
  const detail = {
    id: 'candidate-uuid',
    workspace_id: 'workspace-uuid',
    legacy_candidate_id: 'C001',
    full_name: 'Candidate',
    current_title: 'Engineer',
    summary: 'Experienced developer.',
    skills: [],
    sources: [],
    experience_years: 6,
    location: 'Remote',
    associated_jobs: [],
  }
  vi.mocked(apiClient.get).mockResolvedValueOnce({ data: detail } as never)

  await expect(fetchCandidate('workspace-uuid', 'candidate-uuid')).resolves.toEqual(detail)
  expect(apiClient.get).toHaveBeenCalledWith('/candidates/candidate-uuid', {
    params: { workspace_id: 'workspace-uuid' },
  })
})

test('fetches persisted match score buckets for the active workspace', async () => {
  const distribution = {
    experimental_combined_score: {
      score_scale: '0–100 experimental combined score',
      total_scored_matches: 1,
      buckets: [{ range: '0–20', count: 1 }],
    },
    tfidf_similarity: {
      score_scale: '0–100 scale (cosine similarity × 100)',
      total_scored_matches: 1,
      buckets: [{ range: '0–20', count: 1 }],
    },
  }
  vi.mocked(apiClient.get).mockResolvedValueOnce({ data: distribution } as never)

  await expect(fetchMatchScoreDistribution('workspace-7')).resolves.toEqual(distribution)
  expect(apiClient.get).toHaveBeenCalledWith('/matching/score-distribution', {
    params: { workspace_id: 'workspace-7' },
  })
})
