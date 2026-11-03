import { vi, beforeEach } from 'vitest'

vi.mock('../services/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))
vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({ selectedWorkspace: { workspace_id: 'ws-1' }, loading: false }),
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { apiClient } from '../services/apiClient'
import ShortlistsPage from './ShortlistsPage'

const shortlistData = [{
  shortlist_id: 's1',
  job_id: 'j1',
  candidate_id: 'c1',
  job_title: 'Job A',
  candidate_name: 'Alice',
  current_title: 'Dev',
  status: 'ACTIVE',
}]
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
const candidateData = [
  {
    id: 'c1',
    full_name: 'Alice',
    summary: '',
    current_title: 'Dev',
    location: null,
    experience_years: 5,
    skills: [],
    sources: [],
  },
  {
    id: 'c2',
    full_name: 'Bob',
    summary: '',
    current_title: 'QA',
    location: null,
    experience_years: 2,
    skills: [],
    sources: [],
  },
]
let currentShortlists = shortlistData

const wrap = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<MemoryRouter><QueryClientProvider client={qc}><ShortlistsPage /></QueryClientProvider></MemoryRouter>)
}

beforeEach(() => {
  currentShortlists = shortlistData
  vi.mocked(apiClient.get).mockReset()
  vi.mocked(apiClient.post).mockReset()
  vi.mocked(apiClient.delete).mockReset()
  vi.mocked(apiClient.get).mockImplementation((url: string) => Promise.resolve({
    data: url === '/shortlists' ? currentShortlists : url === '/jobs' ? jobData : candidateData,
  }))
})

async function chooseOption(label: string, optionName: string) {
  const user = userEvent.setup()
  await user.click(screen.getByRole('combobox', { name: label }))
  await user.click(await screen.findByRole('option', { name: optionName }))
}

test('Add candidate sends the backend contract and refreshes the shortlist', async () => {
  vi.mocked(apiClient.post).mockResolvedValue({ data: {}, status: 201 } as never)
  wrap()
  await screen.findByRole('link', { name: 'Alice' })

  await chooseOption('Job', 'Job A')
  await chooseOption('Candidate', 'Bob')
  fireEvent.click(screen.getByRole('button', { name: 'Add' }))

  await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/shortlists', {
    workspace_id: 'ws-1',
    job_id: 'j1',
    candidate_id: 'c2',
  }))
  expect(await screen.findByText('Candidate added to the selected job shortlist.')).toBeTruthy()
})

test('Prevents duplicate active entries for the selected job', async () => {
  wrap()
  await screen.findByRole('link', { name: 'Alice' })
  await chooseOption('Job', 'Job A')
  await chooseOption('Candidate', 'Alice')

  expect(screen.getByText('This candidate is already on the selected job shortlist.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled()
  expect(apiClient.post).not.toHaveBeenCalled()
})

test('Reports add failures and blocks a second submission while pending', async () => {
  let rejectAdd!: (error: Error) => void
  vi.mocked(apiClient.post).mockReturnValueOnce(new Promise((_resolve, reject) => {
    rejectAdd = reject
  }) as never)
  wrap()
  await screen.findByRole('link', { name: 'Alice' })
  await chooseOption('Job', 'Job A')
  await chooseOption('Candidate', 'Bob')
  fireEvent.click(screen.getByRole('button', { name: 'Add' }))

  const pendingButton = await screen.findByRole('button', { name: 'Adding...' })
  expect(pendingButton).toBeDisabled()
  fireEvent.click(pendingButton)
  expect(apiClient.post).toHaveBeenCalledTimes(1)
  rejectAdd(new Error('request failed'))
  expect(await screen.findByText('Failed to add')).toBeTruthy()
})

test('Removal requires confirmation and refreshes the list on success', async () => {
  vi.mocked(apiClient.delete).mockImplementation(async () => {
    currentShortlists = []
    return { status: 204 } as never
  })
  wrap()
  await screen.findByRole('link', { name: 'Alice' })
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
  expect(screen.getByText('Confirm removal of Alice from Job A?')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))

  await waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith('/shortlists/s1', { params: { workspace_id: 'ws-1' } }))
  await waitFor(() => expect(screen.queryByRole('link', { name: 'Alice' })).toBeNull())
})

test('Removal failure is reported and confirmation stays open', async () => {
  vi.mocked(apiClient.delete).mockRejectedValue(new Error('request failed'))
  wrap()
  await screen.findByRole('link', { name: 'Alice' })
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))

  expect(await screen.findByText('Failed to remove candidate.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Confirm' })).toBeTruthy()
})
