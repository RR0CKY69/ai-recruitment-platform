import { beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({ selectedWorkspace: { workspace_id: 'workspace-1' } }),
}))
vi.mock('../services/apiClient', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))
vi.mock('../components/layout/Sidebar', () => ({ default: () => null }))

import { apiClient } from '../services/apiClient'
import CandidatesPage from './CandidatesPage'
import CandidateDetailPage from './CandidateDetailPage'

const candidateListResponse = [{
  id: 'candidate-1',
  workspace_id: 'workspace-1',
  legacy_candidate_id: 'C001',
  full_name: 'Candidate One',
  email: 'candidate@example.test',
  current_title: 'Platform Engineer',
  summary: 'Builds reliable systems.',
  skills: [{ name: 'Python', normalized_name: 'python', years_experience: 5 }],
  sources: [{ provider: 'candidate_provided', source_record_id: 'C001', source_url: 'https://example.test/profile', authorized_basis: 'Candidate provided profile' }],
  experience_years: 6,
  location: 'Remote',
}]

const candidateDetailResponse = {
  ...candidateListResponse[0],
  sources: [
    ...candidateListResponse[0].sources,
    { provider: 'referral', source_record_id: 'R001', source_url: null, authorized_basis: 'Candidate referral' },
  ],
  associated_jobs: [{
    job_id: 'job-1',
    title: 'Platform Engineer',
    status: 'OPEN',
    stage: 'SOURCED',
    matching_results: [{
      model_name: 'tfidf-cosine',
      model_version: '1.0',
      tfidf_similarity: 0.75,
      skill_coverage: 0.5,
      experience_compatibility: 'Meets minimum',
      location_compatibility: 'Exact match',
      hybrid_score: 68,
      updated_at: '2026-11-01T10:00:00Z',
    }],
  }],
}

const jobsResponse = [{
  id: 'job-1',
  workspace_id: 'workspace-1',
  legacy_job_id: 'J001',
  title: 'Platform Engineer',
  description: 'Build reliable systems.',
  required_skills: ['Python'],
  minimum_experience_years: 4,
  location: 'Remote',
  employment_type: 'Full-time',
  status: 'OPEN',
  candidate_count: 1,
}]

function renderCandidates(initialEntry = '/candidates') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/candidates" element={<CandidatesPage />} />
          <Route path="/candidates/:candidateId" element={<CandidateDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

async function selectJob() {
  const user = userEvent.setup()
  const select = await screen.findByRole('combobox', { name: 'Select a job in this workspace' })
  await user.click(select)
  await user.click(await screen.findByRole('option', { name: 'Platform Engineer' }))
}

test('candidate name opens a full profile and adds the candidate to a selected workspace job', async () => {
  let activeShortlist: { candidate_id: string; job_id: string; status: string }[] = []
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/candidates') return { data: candidateListResponse } as never
    if (url === '/candidates/candidate-1') return { data: candidateDetailResponse } as never
    if (url === '/jobs') return { data: jobsResponse } as never
    if (url === '/shortlists') return { data: activeShortlist } as never
    throw new Error(`Unexpected GET ${url}`)
  })

  vi.mocked(apiClient.post).mockImplementation(async (url, payload) => {
    if (url !== '/shortlists') throw new Error(`Unexpected POST ${url}`)
    if (
      typeof payload !== 'object' ||
      payload === null ||
      !('candidate_id' in payload) ||
      !('job_id' in payload) ||
      typeof payload.candidate_id !== 'string' ||
      typeof payload.job_id !== 'string'
    ) {
      throw new Error('Shortlist payload does not match the backend contract')
    }
    activeShortlist = [{ candidate_id: payload.candidate_id, job_id: payload.job_id, status: 'ACTIVE' }]
    return { data: { status: 'ACTIVE' } } as never
  })

  renderCandidates()
  fireEvent.click(await screen.findByRole('link', { name: 'Candidate One' }))

  expect(await screen.findByText('Builds reliable systems.')).toBeInTheDocument()
  expect(screen.getByText('Python (5 years)')).toBeInTheDocument()
  expect(screen.getByText('6 years')).toBeInTheDocument()
  expect(screen.getByText('Remote')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Platform Engineer' })).toHaveAttribute('href', '/jobs/job-1')
  expect(screen.getByText(/TF-IDF 75%/)).toBeInTheDocument()
  expect(screen.getByText('candidate_provided')).toBeInTheDocument()
  expect(screen.getByText('candidate@example.test')).toBeInTheDocument()

  await selectJob()
  fireEvent.click(screen.getByRole('button', { name: 'Add to shortlist' }))
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/shortlists', {
    workspace_id: 'workspace-1',
    job_id: 'job-1',
    candidate_id: 'candidate-1',
  }))
  expect(await screen.findByText('Candidate added to the selected job shortlist.')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: 'Already shortlisted' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Already shortlisted' }))
  expect(apiClient.post).toHaveBeenCalledTimes(1)
})

test('candidate search filters actual workspace candidates and clear restores the results', async () => {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/candidates') return { data: candidateListResponse } as never
    throw new Error(`Unexpected GET ${url}`)
  })

  renderCandidates()
  expect(await screen.findByRole('link', { name: 'Candidate One' })).toBeInTheDocument()
  fireEvent.change(screen.getByRole('textbox', { name: 'Search candidates' }), { target: { value: 'absent' } })
  expect(screen.getByText('No matching candidates')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Clear search candidates' }))
  expect(await screen.findByRole('link', { name: 'Candidate One' })).toBeInTheDocument()
})

test('candidate profile and job query failures are shown', async () => {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/candidates/candidate-1') throw new Error('profile failed')
    if (url === '/jobs') throw new Error('jobs failed')
    if (url === '/shortlists') return { data: [] } as never
    throw new Error(`Unexpected GET ${url}`)
  })
  renderCandidates('/candidates/candidate-1')

  expect(await screen.findByRole('alert')).toHaveTextContent('profile failed')
})

test('shortlist failure reports the backend error and duplicate actions remain blocked while pending', async () => {
  let rejectAdd!: (error: Error) => void
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/candidates/candidate-1') return { data: candidateDetailResponse } as never
    if (url === '/jobs') return { data: jobsResponse } as never
    if (url === '/shortlists') return { data: [] } as never
    throw new Error(`Unexpected GET ${url}`)
  })
  vi.mocked(apiClient.post).mockReturnValueOnce(new Promise((_resolve, reject) => { rejectAdd = reject }) as never)
  renderCandidates('/candidates/candidate-1')

  await selectJob()
  const addButton = screen.getByRole('button', { name: 'Add to shortlist' })
  await waitFor(() => expect(addButton).toBeEnabled())
  fireEvent.click(addButton)
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1))
  const pendingButton = await screen.findByRole('button', { name: 'Adding...' })
  expect(pendingButton).toBeDisabled()
  fireEvent.click(pendingButton)
  expect(apiClient.post).toHaveBeenCalledTimes(1)

  rejectAdd(new Error('request failed'))
  expect(await screen.findByRole('alert')).toHaveTextContent('request failed')
})

test('candidate search includes email and filters candidates by skills', async () => {
  const user = userEvent.setup()
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/candidates') return { data: candidateListResponse } as never
    throw new Error(`Unexpected GET ${url}`)
  })
  renderCandidates()
  await screen.findByRole('link', { name: 'Candidate One' })
  await user.type(screen.getByRole('textbox', { name: 'Search candidates' }), 'candidate@example.test')
  expect(screen.getByRole('link', { name: 'Candidate One' })).toBeInTheDocument()
  await user.clear(screen.getByRole('textbox', { name: 'Search candidates' }))
  await user.click(screen.getByRole('combobox', { name: 'Filter candidates by skill' }))
  await user.click(screen.getByRole('option', { name: 'Python' }))
  expect(screen.getByRole('link', { name: 'Candidate One' })).toBeInTheDocument()
})

test('candidate creation displays duplicate validation from the backend', async () => {
  const user = userEvent.setup()
  vi.mocked(apiClient.get).mockResolvedValueOnce({ data: [] } as never)
  vi.mocked(apiClient.post).mockRejectedValueOnce(new Error('A candidate with this email already exists.'))
  renderCandidates()
  await user.click(await screen.findByRole('button', { name: 'Add candidate' }))
  await user.type(screen.getByLabelText(/Full name/), 'Candidate One')
  await user.type(screen.getByLabelText(/Email/), 'candidate@example.test')
  await user.type(screen.getByLabelText(/Professional summary/), 'Experienced engineer.')
  await user.click(screen.getByRole('button', { name: 'Save candidate' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('A candidate with this email already exists.')
  expect(apiClient.post).toHaveBeenCalledWith('/candidates', expect.objectContaining({
    workspace_id: 'workspace-1',
    email: 'candidate@example.test',
  }))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

test('candidate detail edits the existing workspace profile through the API', async () => {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/candidates/candidate-1') return { data: candidateDetailResponse } as never
    if (url === '/jobs') return { data: jobsResponse } as never
    if (url === '/shortlists') return { data: [] } as never
    throw new Error(`Unexpected GET ${url}`)
  })
  vi.mocked(apiClient.put).mockResolvedValueOnce({ data: candidateDetailResponse } as never)
  renderCandidates('/candidates/candidate-1')

  fireEvent.click(await screen.findByRole('button', { name: 'Edit profile' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save candidate' }))

  await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith('/candidates/candidate-1', expect.objectContaining({
    workspace_id: 'workspace-1',
    full_name: 'Candidate One',
    email: 'candidate@example.test',
    sources: candidateDetailResponse.sources,
  })))
})
