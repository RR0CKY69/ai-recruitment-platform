import { beforeEach, expect, test, vi } from 'vitest'

vi.mock('../features/auth/AuthContext', () => ({ useAuth: () => ({ selectedWorkspace: { workspace_id: 'ws-1' }, loading: false }) }))
vi.mock('../services/apiClient', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { apiClient } from '../services/apiClient'
import MatchingPage from './MatchingPage'

const wrap = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<MemoryRouter><QueryClientProvider client={qc}><MatchingPage /></QueryClientProvider></MemoryRouter>)
}

const jobData = [{
  id: 'j1',
  title: 'Job A',
  status: 'OPEN',
  location: 'Remote',
  description: 'Build software',
  required_skills: ['python'],
  minimum_experience_years: 3,
  employment_type: 'FULL_TIME',
  candidate_count: 1,
}]
const matchData = [{
  job_id: 'j1',
  candidate_id: 'c1',
  candidate_name: 'Alice',
  current_title: 'Dev',
  tfidf_similarity: 0.8,
  skill_coverage: 0.5,
  experience_compatibility: 'Meets minimum',
  location_compatibility: 'Exact match',
  semantic_similarity: null,
  hybrid_score: null,
  explanation: { matched_skills: ['python'], missing_skills: ['django'] },
}]

beforeEach(() => {
  vi.resetAllMocks()
})

function mockWorkspaceReads({
  results = matchData,
}: {
  results?: typeof matchData
} = {}) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/jobs') return { data: jobData } as never
    if (url === '/matching') return { data: results } as never
    if (url === '/shortlists') return { data: [] } as never
    throw new Error(`Unexpected GET ${url}`)
  })
}

async function selectJob() {
  const user = userEvent.setup()
  await user.click(await screen.findByRole('combobox', { name: 'Job' }))
  await user.click(await screen.findByRole('option', { name: 'Job A' }))
}

test('enables Run Matching after job selection and calls matching API', async () => {
  mockWorkspaceReads()
  vi.mocked(apiClient.post).mockResolvedValueOnce({ data: [] } as never)
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()

  const runButton = screen.getByRole('button', { name: 'Run Matching' })
  expect(runButton).not.toBeDisabled()

  fireEvent.click(runButton)
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/matching/run', {
    workspace_id: 'ws-1',
    job_id: 'j1',
  }))
})

test('displays stored matching results', async () => {
  mockWorkspaceReads()
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()
  await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
  expect(screen.getByText('80%')).toBeInTheDocument()
  expect(screen.getByText('50%')).toBeInTheDocument()
  expect(screen.getByText('Meets minimum')).toBeInTheDocument()
  expect(screen.getByText('Exact match')).toBeInTheDocument()
  expect(screen.getByText('Matched:')).toBeInTheDocument()
  expect(screen.getAllByText('python')).toHaveLength(2)
  expect(screen.getByText('Missing:')).toBeInTheDocument()
  expect(screen.getByText('django')).toBeInTheDocument()
})

test('empty results', async () => {
  mockWorkspaceReads({ results: [] })
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()
  await waitFor(() => expect(screen.getByText('No stored matching results for this job.')).toBeInTheDocument())
  const runButton = screen.getByRole('button', { name: 'Run Matching' })
  expect(runButton).not.toBeDisabled()
})

test('stored matching API failure is visible', async () => {
  mockWorkspaceReads()
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/jobs') return { data: jobData } as never
    if (url === '/matching') throw new Error('fail')
    if (url === '/shortlists') return { data: [] } as never
    throw new Error(`Unexpected GET ${url}`)
  })
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()
  await waitFor(() => expect(screen.getByText('Failed to load matching results.')).toBeInTheDocument())
})

test('run matching API failure is visible', async () => {
  mockWorkspaceReads()
  vi.mocked(apiClient.post).mockRejectedValueOnce(Object.assign(new Error('fail'), {
    isAxiosError: true,
    response: { status: 400, data: { detail: 'Job not found in workspace.' } },
  }))
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()
  fireEvent.click(screen.getByRole('button', { name: 'Run Matching' }))
  await waitFor(() => expect(screen.getByText('Job not found in workspace.')).toBeInTheDocument())
})

test('shortlists a matched candidate', async () => {
  mockWorkspaceReads()
  vi.mocked(apiClient.post).mockResolvedValueOnce({ data: {}, status: 201 } as never)
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()
  await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
  fireEvent.click(screen.getByText('Shortlist'))
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/shortlists', {
    workspace_id: 'ws-1',
    job_id: 'j1',
    candidate_id: 'c1',
  }))
  expect(await screen.findByText('Candidate added to the shortlist.')).toBeInTheDocument()
  expect(apiClient.post).toHaveBeenCalledTimes(1)
})
