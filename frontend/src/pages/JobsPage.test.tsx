import { beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({ selectedWorkspace: { workspace_id: 'workspace-1' } }),
}))
vi.mock('../components/layout/Sidebar', () => ({ default: () => null }))
vi.mock('../features/dashboard/api', () => ({ fetchJobs: vi.fn(), fetchCandidates: vi.fn() }))
vi.mock('../features/matching/api', () => ({ fetchMatching: vi.fn() }))
vi.mock('../features/assignments/api', () => ({
  fetchJobCandidates: vi.fn(),
  assignCandidateToJob: vi.fn(),
  removeCandidateFromJob: vi.fn(),
}))
vi.mock('../features/jobs/api', () => ({ createJob: vi.fn(), updateJob: vi.fn() }))
vi.mock('../features/candidates/api', () => ({ createCandidate: vi.fn(), updateCandidate: vi.fn(), uploadCandidateResume: vi.fn() }))

import { fetchCandidates, fetchJobs } from '../features/dashboard/api'
import { fetchMatching } from '../features/matching/api'
import { assignCandidateToJob, fetchJobCandidates, removeCandidateFromJob } from '../features/assignments/api'
import { createJob, updateJob } from '../features/jobs/api'
import { createCandidate } from '../features/candidates/api'
import JobsPage from './JobsPage'
import JobDetailPage from './JobDetailPage'

const job = {
  job_id: 'job-1',
  title: 'Platform Engineer',
  status: 'OPEN',
  location: 'Remote',
  description: 'Build reliable services.',
  required_skills: ['Python', 'PostgreSQL'],
  minimum_experience_years: 4,
  employment_type: 'Full-time',
  candidate_count: 1,
}
const workspaceCandidate = {
  candidate_id: 'candidate-1',
  full_name: 'Candidate One',
  current_title: 'Developer',
  summary: 'Builds systems.',
  experience_years: 5,
  location: 'Remote',
  skills: [{ name: 'Python', normalized_name: 'python', years_experience: 3 }],
  sources: [],
}

function renderJobs(initialEntry = '/jobs') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/:jobId" element={<JobDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(fetchCandidates).mockResolvedValue([])
  vi.mocked(fetchJobCandidates).mockResolvedValue([])
  vi.mocked(assignCandidateToJob).mockResolvedValue({
    candidate_id: 'candidate-1',
    full_name: 'Candidate One',
    current_title: 'Developer',
    summary: 'Experienced developer.',
    experience_years: 5,
    location: 'Remote',
    skills: [{ name: 'Python', normalized_name: 'python', years_experience: 3 }],
    sources: [],
    stage: 'SOURCED',
  })
  vi.mocked(removeCandidateFromJob).mockResolvedValue(undefined)
  vi.mocked(createCandidate).mockResolvedValue(workspaceCandidate)
})

test('job title opens workspace-scoped details and existing matching results', async () => {
  vi.mocked(fetchJobs).mockResolvedValue([job])
  vi.mocked(fetchMatching).mockResolvedValue([{
    job_id: 'job-1',
    candidate_id: 'candidate-1',
    candidate_name: 'Candidate One',
    current_title: 'Developer',
    tfidf_similarity: 0.75,
    skill_coverage: 0.5,
    experience_compatibility: 'Meets minimum',
    location_compatibility: 'Exact match',
    semantic_similarity: null,
    hybrid_score: null,
    explanation: { matched_skills: ['Python'] },
  }])

  renderJobs()
  fireEvent.click((await screen.findAllByRole('link', { name: 'Platform Engineer' }))[0])

  expect(await screen.findByText('Build reliable services.')).toBeInTheDocument()
  expect(screen.getByText('Python, PostgreSQL')).toBeInTheDocument()
  expect(screen.getByText('4 years')).toBeInTheDocument()
  expect(screen.getByText('Remote')).toBeInTheDocument()
  expect(screen.getByText('Full-time')).toBeInTheDocument()
  expect(screen.getAllByText('Assigned candidates')).toHaveLength(2)
  expect(screen.getByText('1', { selector: 'p' })).toBeInTheDocument()
  expect(await screen.findByRole('link', { name: 'Candidate One' })).toHaveAttribute('href', '/candidates/candidate-1')
  expect(await screen.findByText('TF-IDF 75%')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Edit job' })).toBeInTheDocument()
  expect(fetchJobs).toHaveBeenCalledWith('workspace-1')
  expect(fetchMatching).toHaveBeenCalledWith('workspace-1', 'job-1')
})

test('job detail displays loading and API failure states', async () => {
  vi.mocked(fetchJobs).mockRejectedValueOnce(new Error('API unavailable'))
  renderJobs('/jobs/job-1')
  expect(await screen.findByRole('alert')).toHaveTextContent('API unavailable')
})

test('matching history errors are visible without hiding job details', async () => {
  vi.mocked(fetchJobs).mockResolvedValue([job])
  vi.mocked(fetchMatching).mockRejectedValueOnce(new Error('API unavailable'))
  renderJobs('/jobs/job-1')

  expect(await screen.findByText('Platform Engineer')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('API unavailable'))
})

test('job search filters actual workspace jobs and clearing restores results', async () => {
  vi.mocked(fetchJobs).mockResolvedValue([
    job,
    {
      ...job,
      job_id: 'job-2',
      title: 'Product Designer',
      required_skills: ['Figma'],
    },
  ])
  renderJobs()

  expect(await screen.findAllByRole('link', { name: 'Platform Engineer' })).toHaveLength(2)
  expect(screen.getAllByRole('link', { name: 'Product Designer' })).toHaveLength(2)
  fireEvent.change(screen.getByRole('textbox', { name: 'Search jobs' }), { target: { value: 'platform' } })
  expect(screen.getAllByRole('link', { name: 'Platform Engineer' })).toHaveLength(2)
  expect(screen.queryByRole('link', { name: 'Product Designer' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Clear search jobs' }))
  expect(await screen.findAllByRole('link', { name: 'Product Designer' })).toHaveLength(2)
})

test('job detail displays explicitly assigned candidate profile and pipeline stage', async () => {
  vi.mocked(fetchJobs).mockResolvedValue([job])
  vi.mocked(fetchCandidates).mockResolvedValue([])
  vi.mocked(fetchJobCandidates).mockResolvedValue([{
    candidate_id: 'candidate-1',
    full_name: 'Candidate One',
    current_title: 'Developer',
    summary: 'Builds services.',
    experience_years: 5,
    location: 'Remote',
    skills: [{ name: 'Python', normalized_name: 'python', years_experience: 3 }],
    sources: [],
    stage: 'REVIEWING',
  }])
  vi.mocked(fetchMatching).mockResolvedValue([])
  renderJobs('/jobs/job-1')

  expect(await screen.findByRole('link', { name: 'Candidate One' })).toHaveAttribute('href', '/candidates/candidate-1')
  expect(screen.getByText('Stage: REVIEWING')).toBeInTheDocument()
  expect(screen.getByText('5 years')).toBeInTheDocument()
  expect(screen.getAllByText('Remote')).toHaveLength(2)
  expect(screen.getByText('Python')).toBeInTheDocument()
})

test('removing a job assignment never deletes the candidate profile', async () => {
  vi.mocked(fetchJobs).mockResolvedValue([job])
  vi.mocked(fetchCandidates).mockResolvedValue([])
  vi.mocked(fetchJobCandidates).mockResolvedValue([{
    candidate_id: 'candidate-1',
    full_name: 'Candidate One',
    current_title: 'Developer',
    summary: 'Builds services.',
    experience_years: 5,
    location: 'Remote',
    skills: [],
    sources: [],
    stage: 'SOURCED',
  }])
  vi.mocked(fetchMatching).mockResolvedValue([])
  renderJobs('/jobs/job-1')

  fireEvent.click(await screen.findByRole('button', { name: 'Remove from job' }))
  const confirmation = screen.getByRole('alertdialog')
  expect(confirmation).toHaveTextContent('workspace profile will remain')
  fireEvent.click(screen.getByRole('button', { name: 'Remove assignment' }))

  await waitFor(() => expect(removeCandidateFromJob).toHaveBeenCalledWith('workspace-1', 'job-1', 'candidate-1'))
  expect(screen.queryByRole('button', { name: 'Delete candidate' })).not.toBeInTheDocument()
})

test('job creation sends entered details and keeps backend errors visible', async () => {
  const user = userEvent.setup()
  vi.mocked(fetchJobs).mockResolvedValue([])
  vi.mocked(createJob).mockRejectedValueOnce(new Error('Job creation is not available yet.'))
  renderJobs()
  await user.click(await screen.findByRole('button', { name: 'Create job' }))
  await user.type(screen.getByLabelText(/Job title/), 'Data Engineer')
  await user.type(screen.getByLabelText(/Job description/), 'Build data services.')
  await user.type(screen.getByLabelText(/Required skills/), 'Python, SQL')
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Create job' }))

  expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Job creation is not available yet.')
  expect(createJob).toHaveBeenCalledWith(expect.objectContaining({
    workspace_id: 'workspace-1',
    title: 'Data Engineer',
    description: 'Build data services.',
    required_skills: ['Python', 'SQL'],
  }))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

test('job status filter limits the workspace listing', async () => {
  const user = userEvent.setup()
  vi.mocked(fetchJobs).mockResolvedValue([
    job,
    { ...job, job_id: 'job-2', title: 'Closed role', status: 'CLOSED' },
  ])
  renderJobs()
  expect(await screen.findAllByRole('link', { name: 'Closed role' })).toHaveLength(2)
  await user.click(screen.getByRole('combobox', { name: 'Filter jobs by status' }))
  await user.click(screen.getByRole('option', { name: 'CLOSED' }))
  expect(screen.getAllByRole('link', { name: 'Closed role' })).toHaveLength(2)
  expect(screen.queryByRole('link', { name: 'Platform Engineer' })).not.toBeInTheDocument()
})

test('job editor updates existing role fields and closes only after API success', async () => {
  const user = userEvent.setup()
  vi.mocked(fetchJobs).mockResolvedValue([job])
  vi.mocked(updateJob).mockResolvedValue({ ...job, title: 'Updated Platform Engineer', status: 'CLOSED' })
  renderJobs()
  await user.click((await screen.findAllByRole('button', { name: 'Edit Platform Engineer' }))[0])
  expect(screen.getByLabelText(/Job title/)).toHaveValue('Platform Engineer')
  await user.clear(screen.getByLabelText(/Job title/))
  await user.type(screen.getByLabelText(/Job title/), 'Updated Platform Engineer')
  await user.click(screen.getByRole('combobox', { name: 'Job status' }))
  await user.click(screen.getByRole('option', { name: 'CLOSED' }))
  await user.click(screen.getByRole('button', { name: 'Save changes' }))

  await waitFor(() => expect(updateJob).toHaveBeenCalledWith('workspace-1', 'job-1', expect.objectContaining({
    title: 'Updated Platform Engineer',
    status: 'CLOSED',
  })))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

test('job listing reports API errors', async () => {
  vi.mocked(fetchJobs).mockRejectedValueOnce(new Error('Workspace jobs unavailable'))
  renderJobs()
  expect(await screen.findByRole('alert')).toHaveTextContent('Workspace jobs unavailable')
})

test('job assignment picker shows profile details and assigns only a workspace candidate once', async () => {
  const user = userEvent.setup()
  vi.mocked(fetchJobs).mockResolvedValue([job])
  vi.mocked(fetchCandidates).mockResolvedValue([workspaceCandidate])
  vi.mocked(fetchJobCandidates).mockResolvedValue([])
  vi.mocked(fetchMatching).mockResolvedValue([])
  renderJobs('/jobs/job-1')

  await user.click(await screen.findByRole('button', { name: 'Add existing candidate' }))
  expect(await screen.findByRole('link', { name: 'Candidate One' })).toHaveAttribute('href', '/candidates/candidate-1')
  expect(screen.getByText('5 years · Remote')).toBeInTheDocument()
  expect(screen.getByText('Python')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Assign' }))

  await waitFor(() => expect(assignCandidateToJob).toHaveBeenCalledWith('job-1', {
    workspace_id: 'workspace-1',
    candidate_id: 'candidate-1',
  }))
})

test('assignment picker omits a candidate who is already assigned', async () => {
  const user = userEvent.setup()
  vi.mocked(fetchJobs).mockResolvedValue([job])
  vi.mocked(fetchCandidates).mockResolvedValue([workspaceCandidate])
  vi.mocked(fetchJobCandidates).mockResolvedValue([{ ...workspaceCandidate, stage: 'SOURCED' }])
  vi.mocked(fetchMatching).mockResolvedValue([])
  renderJobs('/jobs/job-1')

  await user.click(await screen.findByRole('button', { name: 'Add existing candidate' }))
  expect(await screen.findByText('No unassigned candidates match this search.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Assign' })).not.toBeInTheDocument()
  expect(assignCandidateToJob).not.toHaveBeenCalled()
})

test('job assignment API errors are visible and prevent unsafe assignment attempts', async () => {
  const user = userEvent.setup()
  vi.mocked(fetchJobs).mockResolvedValue([job])
  vi.mocked(fetchCandidates).mockResolvedValue([workspaceCandidate])
  vi.mocked(fetchJobCandidates).mockRejectedValue(new Error('Assignment API is not available.'))
  vi.mocked(fetchMatching).mockResolvedValue([])
  renderJobs('/jobs/job-1')

  expect(await screen.findByText('Assignment API is not available.')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Add existing candidate' }))
  expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Assignments could not be loaded')
  expect(screen.getByRole('button', { name: 'Assign' })).toBeDisabled()
  expect(assignCandidateToJob).not.toHaveBeenCalled()
})

test('creates and assigns a profile while preserving it if assignment fails', async () => {
  const user = userEvent.setup()
  vi.mocked(fetchJobs).mockResolvedValue([job])
  vi.mocked(fetchCandidates).mockResolvedValue([])
  vi.mocked(fetchJobCandidates).mockResolvedValue([])
  vi.mocked(fetchMatching).mockResolvedValue([])
  vi.mocked(assignCandidateToJob).mockRejectedValueOnce(new Error('Assignment API unavailable'))
  vi.mocked(createCandidate).mockResolvedValueOnce({ ...workspaceCandidate, full_name: 'New Candidate' })
  renderJobs('/jobs/job-1')

  await user.click(await screen.findByRole('button', { name: 'Create and assign' }))
  await user.type(screen.getByLabelText(/Full name/), 'New Candidate')
  await user.type(screen.getByLabelText(/Email/), 'new@example.test')
  await user.type(screen.getByLabelText(/Professional summary/), 'Experienced engineer.')
  await user.click(screen.getByRole('button', { name: 'Save candidate' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Candidate profile was created, but assignment failed')
  expect(await screen.findByRole('link', { name: 'View New Candidate' })).toHaveAttribute('href', '/candidates/candidate-1')
  expect(createCandidate).toHaveBeenCalledWith(expect.objectContaining({
    workspace_id: 'workspace-1',
    full_name: 'New Candidate',
  }))
  expect(assignCandidateToJob).toHaveBeenCalledWith('job-1', {
    workspace_id: 'workspace-1',
    candidate_id: 'candidate-1',
  })
})
