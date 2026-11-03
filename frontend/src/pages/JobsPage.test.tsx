import { beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({ selectedWorkspace: { workspace_id: 'workspace-1' } }),
}))
vi.mock('../components/layout/Sidebar', () => ({ default: () => null }))
vi.mock('../features/dashboard/api', () => ({ fetchJobs: vi.fn() }))
vi.mock('../features/matching/api', () => ({ fetchMatching: vi.fn() }))

import { fetchJobs } from '../features/dashboard/api'
import { fetchMatching } from '../features/matching/api'
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

beforeEach(() => vi.clearAllMocks())

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
  fireEvent.click(await screen.findByRole('link', { name: 'Platform Engineer' }))

  expect(await screen.findByText('Build reliable services.')).toBeInTheDocument()
  expect(screen.getByText('Python, PostgreSQL')).toBeInTheDocument()
  expect(screen.getByText('4 years')).toBeInTheDocument()
  expect(screen.getByText('Remote')).toBeInTheDocument()
  expect(screen.getByText('Full-time')).toBeInTheDocument()
  expect(screen.getByText('Matched candidates')).toBeInTheDocument()
  expect(screen.getByText('1', { selector: 'p' })).toBeInTheDocument()
  expect(await screen.findByRole('link', { name: 'Candidate One' })).toHaveAttribute('href', '/candidates/candidate-1')
  expect(await screen.findByText('TF-IDF 75%')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
  expect(fetchJobs).toHaveBeenCalledWith('workspace-1')
  expect(fetchMatching).toHaveBeenCalledWith('workspace-1', 'job-1')
})

test('job detail displays loading and API failure states', async () => {
  vi.mocked(fetchJobs).mockRejectedValueOnce(new Error('API unavailable'))
  renderJobs('/jobs/job-1')
  expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load job details.')
})

test('matching history errors are visible without hiding job details', async () => {
  vi.mocked(fetchJobs).mockResolvedValue([job])
  vi.mocked(fetchMatching).mockRejectedValueOnce(new Error('API unavailable'))
  renderJobs('/jobs/job-1')

  expect(await screen.findByText('Platform Engineer')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Failed to load matching results.'))
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

  expect(await screen.findByRole('link', { name: 'Platform Engineer' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Product Designer' })).toBeInTheDocument()
  fireEvent.change(screen.getByRole('textbox', { name: 'Search jobs' }), { target: { value: 'platform' } })
  expect(screen.getByRole('link', { name: 'Platform Engineer' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Product Designer' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Clear search jobs' }))
  expect(await screen.findByRole('link', { name: 'Product Designer' })).toBeInTheDocument()
})
