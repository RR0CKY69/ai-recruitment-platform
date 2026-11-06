import { beforeEach, expect, test, vi } from 'vitest'

vi.mock('../services/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}))
vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({ selectedWorkspace: { workspace_id: 'ws-1' }, loading: false }),
}))

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { apiClient } from '../services/apiClient'
import PipelinePage from './PipelinePage'

const jobData = [
  {
    id: 'job-1',
    title: 'Job A',
    status: 'OPEN',
    location: 'Remote',
    description: 'Build software',
    required_skills: ['python'],
    minimum_experience_years: 3,
    employment_type: 'FULL_TIME',
    candidate_count: 2,
  },
  {
    id: 'job-2',
    title: 'Job B',
    status: 'OPEN',
    location: 'Remote',
    description: 'Design systems',
    required_skills: ['figma'],
    minimum_experience_years: 2,
    employment_type: 'FULL_TIME',
    candidate_count: 1,
  },
]

const job1Candidates = [
  {
    candidate_id: 'c1',
    full_name: 'Alice',
    current_title: 'Developer',
    summary: 'Strong backend developer.',
    experience_years: 5,
    location: 'Remote',
    skills: [{ name: 'python', normalized_name: 'python', years_experience: 4 }],
    sources: [],
    stage: 'SOURCED',
  },
  {
    candidate_id: 'c2',
    full_name: 'Bob',
    current_title: 'QA Engineer',
    summary: 'Quality-focused engineer.',
    experience_years: 3,
    location: 'Remote',
    skills: [{ name: 'testing', normalized_name: 'testing', years_experience: 2 }],
    sources: [],
    stage: 'SHORTLISTED',
  },
]

const job2Candidates = [
  {
    candidate_id: 'c3',
    full_name: 'Carol',
    current_title: 'Designer',
    summary: 'UI-focused.',
    experience_years: 4,
    location: 'Remote',
    skills: [],
    sources: [],
    stage: 'SOURCED',
  },
]

const matchingData: never[] = []

let currentJob1Candidates: typeof job1Candidates
let currentJob2Candidates: typeof job2Candidates

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <PipelinePage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

async function selectJob(user: ReturnType<typeof userEvent.setup>, title: string) {
  await user.click(await screen.findByRole('combobox', { name: 'Job' }))
  await user.click(await screen.findByRole('option', { name: title }))
}

async function changeStage(
  user: ReturnType<typeof userEvent.setup>,
  candidateName: string,
  newStage: string,
) {
  await user.click(await screen.findByRole('combobox', { name: `Stage for ${candidateName}` }))
  await user.click(await screen.findByRole('option', { name: newStage }))
}

beforeEach(() => {
  currentJob1Candidates = [...job1Candidates]
  currentJob2Candidates = [...job2Candidates]

  vi.clearAllMocks()

  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === '/jobs') return { data: jobData } as never
    if (url === '/jobs/job-1/candidates') return { data: currentJob1Candidates } as never
    if (url === '/jobs/job-2/candidates') return { data: currentJob2Candidates } as never
    if (url === '/matching') return { data: matchingData } as never
    throw new Error(`Unexpected GET ${url}`)
  })

  vi.mocked(apiClient.patch).mockImplementation(async (url: string, body: unknown) => {
    const match = url.match(/^\/jobs\/(job-\d)\/candidates\/(c\d+)$/)
    if (!match) throw new Error(`Unexpected PATCH ${url}`)
    const [, jobId, candidateId] = match
    const stage = (body as { stage?: string } | undefined)?.stage ?? 'SOURCED'
    const candidates = jobId === 'job-1' ? currentJob1Candidates : currentJob2Candidates
    const candidate = candidates.find(c => c.candidate_id === candidateId)
    if (!candidate) throw new Error('Candidate not found')
    candidate.stage = stage
    return { data: { ...candidate, stage } } as never
  })
})

test('displays all five recruitment stages as grouped pipeline columns', async () => {
  const user = userEvent.setup()
  renderPage()

  await selectJob(user, 'Job A')

  await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())

  for (const stage of ['SOURCED', 'REVIEWING', 'SHORTLISTED', 'REJECTED', 'HIRED']) {
    expect(screen.getByRole('heading', { name: stage })).toBeInTheDocument()
  }
})

test('updates a candidate stage and moves them to the correct column', async () => {
  const user = userEvent.setup()
  renderPage()

  await selectJob(user, 'Job A')
  await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())

  await changeStage(user, 'Alice', 'REVIEWING')

  await waitFor(() =>
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/jobs/job-1/candidates/c1',
      { stage: 'REVIEWING' },
      { params: { workspace_id: 'ws-1' } },
    ),
  )

  await waitFor(() => {
    const reviewHeading = screen.getByRole('heading', { name: 'REVIEWING' })
    const reviewSection = reviewHeading.closest('section')
    expect(reviewSection).toContainElement(screen.getByText('Alice'))
  })
})

test('sends the correct job ID, candidate ID, workspace ID and stage to the API', async () => {
  const user = userEvent.setup()
  renderPage()

  await selectJob(user, 'Job A')
  await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())

  await changeStage(user, 'Alice', 'HIRED')

  await waitFor(() =>
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/jobs/job-1/candidates/c1',
      { stage: 'HIRED' },
      { params: { workspace_id: 'ws-1' } },
    ),
  )
})

test('displays an error when the stage update fails', async () => {
  vi.mocked(apiClient.patch).mockRejectedValueOnce(new Error('boom'))

  const user = userEvent.setup()
  renderPage()

  await selectJob(user, 'Job A')
  await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())

  await changeStage(user, 'Alice', 'REVIEWING')

  await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument())
})

test('prevents duplicate submissions while saving', async () => {
  let resolvePatch!: (value: unknown) => void
  const patchPromise = new Promise<unknown>(resolve => {
    resolvePatch = resolve
  })
  vi.mocked(apiClient.patch).mockResolvedValueOnce(patchPromise as never)

  const user = userEvent.setup()
  renderPage()

  await selectJob(user, 'Job A')
  await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())

  await changeStage(user, 'Alice', 'REVIEWING')

  // While saving, the dropdown is disabled, so a second submission cannot be triggered.
  const stageCombo = screen.getByRole('combobox', { name: 'Stage for Alice' })
  expect(stageCombo).toBeDisabled()

  expect(apiClient.patch).toHaveBeenCalledTimes(1)

  resolvePatch({ data: { candidate_id: 'c1', stage: 'REVIEWING' } })
  await waitFor(() => expect(apiClient.patch).toHaveBeenCalledTimes(1))
})

test('switching jobs displays only the selected job candidates', async () => {
  const user = userEvent.setup()
  renderPage()

  await selectJob(user, 'Job A')
  await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())
  expect(screen.queryByText('Carol')).toBeNull()

  await selectJob(user, 'Job B')
  await waitFor(() => expect(screen.getByText('Carol')).toBeInTheDocument())
  expect(screen.queryByText('Alice')).toBeNull()
})

test('stage changes for one job do not affect another job assignment', async () => {
  const user = userEvent.setup()
  renderPage()

  await selectJob(user, 'Job A')
  await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument())

  await changeStage(user, 'Alice', 'REVIEWING')

  await waitFor(() =>
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/jobs/job-1/candidates/c1',
      { stage: 'REVIEWING' },
      { params: { workspace_id: 'ws-1' } },
    ),
  )

  await selectJob(user, 'Job B')
  await waitFor(() => expect(screen.getByText('Carol')).toBeInTheDocument())

  const job2PatchCalls = vi.mocked(apiClient.patch).mock.calls.filter(([url]) =>
    url.includes('/jobs/job-2/candidates/'),
  )
  expect(job2PatchCalls).toHaveLength(0)
})
