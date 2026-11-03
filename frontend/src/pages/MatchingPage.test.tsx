import { vi, beforeEach } from 'vitest'

vi.mock('../features/auth/AuthContext', () => ({ useAuth: () => ({ selectedWorkspace: { workspace_id: 'ws-1' }, loading: false }) }))
vi.mock('../services/apiClient', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { apiClient } from '../services/apiClient'
import MatchingPage from './MatchingPage'

const wrap = () => { const qc = new QueryClient(); return render(<MemoryRouter><QueryClientProvider client={qc}><MatchingPage /></QueryClientProvider></MemoryRouter>) }

const jobData = [{ id: 'j1', title: 'Job A', status: 'OPEN', location: 'Remote', description: 'Build software', required_skills: ['python'], minimum_experience_years: 3, employment_type: 'FULL_TIME', candidate_count: 2 }]
const matchData = [{ job_id: 'j1', candidate_id: 'c1', candidate_name: 'Alice', current_title: 'Dev', tfidf_similarity: 0.8, skill_coverage: 0.5, experience_compatibility: 'Meets minimum', location_compatibility: 'Exact match', semantic_similarity: null, hybrid_score: null, explanation: { matched_skills: ['python'], missing_skills: ['django'] } }]

beforeEach(() => { (apiClient.get as any).mockReset(); (apiClient.post as any).mockReset() })

async function selectJob() {
  const user = userEvent.setup()
  await user.click(await screen.findByRole('combobox', { name: 'Job' }))
  await user.click(await screen.findByRole('option', { name: 'Job A' }))
}

test('Job selection and run matching', async () => {
  (apiClient.get as any).mockResolvedValue({ data: jobData });
  (apiClient.post as any).mockResolvedValue({ data: matchData })
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()
  fireEvent.click(screen.getByText('Run Matching'))
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/matching/run', { workspace_id: 'ws-1', job_id: 'j1' }))
})

test('Display results', async () => {
  (apiClient.get as any).mockResolvedValue({ data: jobData });
  ;(apiClient.get as any).mockResolvedValueOnce({ data: jobData }).mockResolvedValueOnce({ data: matchData })
  ;(apiClient.post as any).mockResolvedValue({ data: matchData })
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()
  fireEvent.click(screen.getByText('Run Matching'))
  await waitFor(() => expect(screen.getByText('Alice')).toBeTruthy())
  expect(screen.getByText('80%')).toBeTruthy()
  expect(screen.getByText('50%')).toBeTruthy()
  expect(screen.getByText('Meets minimum')).toBeTruthy()
  expect(screen.getByText('Exact match')).toBeTruthy()
  expect(screen.getByText('Matched:')).toBeTruthy()
  expect(screen.getAllByText('python')).toHaveLength(2)
  expect(screen.getByText('Missing:')).toBeTruthy()
  expect(screen.getByText('django')).toBeTruthy()
})

test('Empty results', async () => {
  (apiClient.get as any).mockResolvedValue({ data: jobData });
  ;(apiClient.post as any).mockResolvedValue({ data: [] })
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()
  fireEvent.click(screen.getByText('Run Matching'))
  await waitFor(() => expect(screen.getByText('No matching results. Run matching.')).toBeTruthy())
})

test('API failure', async () => {
  (apiClient.get as any).mockImplementation((url: string) => Promise.resolve({ data: url === '/jobs' ? jobData : [] }))
  ;(apiClient.post as any).mockRejectedValue(new Error('fail'))
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()
  fireEvent.click(screen.getByText('Run Matching'))
  await waitFor(() => expect(screen.getByText('Matching failed.')).toBeTruthy())
})

test('Shortlist matched candidate', async () => {
  (apiClient.get as any).mockImplementation((url: string) => Promise.resolve({
    data: url === '/jobs' ? jobData : url === '/matching' ? matchData : [],
  }))
  ;(apiClient.post as any).mockResolvedValueOnce({ data: matchData, status: 200 }).mockResolvedValueOnce({ data: {}, status: 201 })
  wrap()
  await screen.findByRole('combobox', { name: 'Job' })
  await selectJob()
  fireEvent.click(screen.getByText('Run Matching'))
  await waitFor(() => expect(screen.getByText('Alice')).toBeTruthy())
  fireEvent.click(screen.getByText('Shortlist'))
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/shortlists', { workspace_id: 'ws-1', job_id: 'j1', candidate_id: 'c1' }))
  expect(await screen.findByText('Candidate added to the shortlist.')).toBeTruthy()
})