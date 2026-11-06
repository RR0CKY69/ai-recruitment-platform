
import { beforeEach, vi } from 'vitest'

vi.mock('../services/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
  },
}))

vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({
    selectedWorkspace: { workspace_id: 'ws-1' },
    user: { id: 'reviewer-1', full_name: 'Reviewer One' },
    loading: false,
  }),
}))

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { apiClient } from '../services/apiClient'
import EvaluationsPage from './EvaluationsPage'

const ownEvaluation = {
  evaluation_id: 'evaluation-1',
  workspace_id: 'ws-1',
  job_id: 'job-1',
  legacy_job_id: 'J001',
  job_title: 'Job A',
  candidate_id: 'candidate-1',
  legacy_candidate_id: 'C001',
  candidate_name: 'Alice',
  current_title: 'Developer',
  relevance_label: 1,
  review_status: 'reviewed' as const,
  reviewer_id: 'reviewer-1',
  reviewer_name: 'Reviewer One',
  notes: [{
    note_id: 'note-1',
    author_id: 'reviewer-1',
    author_name: 'Reviewer One',
    note: 'Existing feedback',
  }],
  updated_at: '2024-01-01T00:00:00Z',
}

const otherReviewerEvaluation = {
  ...ownEvaluation,
  evaluation_id: 'evaluation-2',
  reviewer_id: 'reviewer-2',
  reviewer_name: 'Reviewer Two',
  relevance_label: 2,
  notes: [{
    note_id: 'note-2',
    author_id: 'reviewer-2',
    author_name: 'Reviewer Two',
    note: 'Another reviewer feedback',
  }],
}

const unassignedEvaluation = {
  ...ownEvaluation,
  evaluation_id: 'evaluation-3',
  candidate_id: 'candidate-2',
  candidate_name: 'Bob',
  notes: [{
    note_id: 'note-3',
    author_id: 'reviewer-1',
    author_name: 'Reviewer One',
    note: 'Unassigned candidate feedback',
  }],
}

const jobData = [
  {
    id: 'job-1',
    title: 'Job A',
    status: 'OPEN',
    description: 'Developer role',
    required_skills: ['React'],
    minimum_experience_years: 2,
    employment_type: 'Full-time',
    location: 'Remote',
    candidate_count: 1,
  },
  {
    id: 'job-2',
    title: 'Job B',
    status: 'OPEN',
    description: 'Backend role',
    required_skills: ['Python'],
    minimum_experience_years: 2,
    employment_type: 'Full-time',
    location: 'Remote',
    candidate_count: 1,
  },
]

const assignedCandidates = [
  {
    candidate_id: 'candidate-1',
    full_name: 'Alice',
    email: 'alice@example.com',
    current_title: 'Developer',
    summary: 'React Developer',
    experience_years: 3,
    location: 'Remote',
    skills: [],
    sources: [],
    stage: 'REVIEWING',
  },
]

const jobBCandidates = [
  {
    candidate_id: 'candidate-2',
    full_name: 'Bob',
    email: 'bob@example.com',
    current_title: 'Backend Developer',
    summary: 'Python Developer',
    experience_years: 3,
    location: 'Remote',
    skills: [],
    sources: [],
    stage: 'REVIEWING',
  },
]

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <EvaluationsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

function mockEvaluations(...responses: object[][]) {
  const get = apiClient.get as any
  let evaluationCall = 0

  get.mockImplementation((url: string) => {
    if (url === '/jobs') {
      return Promise.resolve({ data: jobData })
    }

    if (url === '/jobs/job-1/candidates') {
      return Promise.resolve({ data: assignedCandidates })
    }

    if (url === '/jobs/job-2/candidates') {
      return Promise.resolve({ data: jobBCandidates })
    }

    if (url === '/evaluations') {
      const response =
        responses[Math.min(evaluationCall, responses.length - 1)]

      evaluationCall += 1

      return Promise.resolve({ data: response })
    }

    return Promise.reject(new Error(`Unexpected GET request: ${url}`))
  })
}

function mockSaveError(status: number) {
  ;(apiClient.put as any).mockRejectedValue(
    Object.assign(new Error('Request failed'), {
      isAxiosError: true,
      response: { status },
    }),
  )
}

beforeEach(() => {
  ;(apiClient.get as any).mockReset()
  ;(apiClient.put as any).mockReset()
})

test('prefills the current reviewer label and existing feedback for editing', async () => {
  const user = userEvent.setup()
  mockEvaluations([ownEvaluation, otherReviewerEvaluation])
  renderPage()

  const ownRow = (await screen.findByText('Existing feedback')).closest('tr')
  expect(ownRow).not.toBeNull()

  const ownEditButton = within(ownRow!).getByRole('button', { name: 'Edit' })
  expect(ownEditButton).toBeEnabled()
  await user.click(ownEditButton)

  const dialog = await screen.findByRole('dialog', { name: 'Edit evaluation' })
  expect(dialog).toBeVisible()
  expect(dialog).toHaveClass('fixed', 'inset-0')

  expect(screen.getByText('Another reviewer feedback').closest('tr')).toHaveTextContent('Read-only')
  expect(screen.getByRole('combobox', { name: 'Relevance label' })).toHaveTextContent('1 - Partial')
  expect(screen.getByRole('textbox', { name: 'Feedback' })).toHaveValue('Existing feedback')
})

test('updates the existing note using its note ID without creating a duplicate', async () => {
  const user = userEvent.setup()
  mockEvaluations([ownEvaluation])
  ;(apiClient.put as any).mockResolvedValue({ data: {} })
  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))

  const feedback = screen.getByRole('textbox', { name: 'Feedback' })
  await user.clear(feedback)
  await user.type(feedback, 'Revised feedback')
  await user.click(screen.getByRole('button', { name: 'Save' }))

  await waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(1))

  expect(apiClient.put).toHaveBeenCalledWith('/evaluations', {
    workspace_id: 'ws-1',
    job_id: 'job-1',
    candidate_id: 'candidate-1',
    relevance_label: 1,
    review_status: 'reviewed',
    note: 'Revised feedback',
    note_id: 'note-1',
    expected_updated_at: '2024-01-01T00:00:00Z',
  })
})

test('keeps another reviewer evaluation visible but read-only', async () => {
  mockEvaluations([otherReviewerEvaluation])
  renderPage()

  expect(await screen.findByText('Alice')).toBeInTheDocument()
  expect(screen.getByText('Another reviewer feedback')).toBeInTheDocument()
  expect(screen.getByText('Read-only')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
})

test('excludes evaluations for candidates not assigned to the selected job', async () => {
  mockEvaluations([ownEvaluation, unassignedEvaluation])
  renderPage()

  expect(await screen.findByText('Alice')).toBeInTheDocument()
  expect(screen.getByText('Existing feedback')).toBeInTheDocument()

  expect(screen.queryByText('Bob')).not.toBeInTheDocument()
  expect(screen.queryByText('Unassigned candidate feedback')).not.toBeInTheDocument()
})

test('shows only evaluations for the newly selected job', async () => {
  const user = userEvent.setup()

  mockEvaluations([
    ownEvaluation,
    {
      ...ownEvaluation,
      evaluation_id: 'evaluation-job-2',
      job_id: 'job-2',
      job_title: 'Job B',
      candidate_id: 'candidate-2',
      candidate_name: 'Bob',
      notes: [{
        note_id: 'note-job-2',
        author_id: 'reviewer-1',
        author_name: 'Reviewer One',
        note: 'Job B feedback',
      }],
    },
  ])

  renderPage()

  expect(await screen.findByText('Alice')).toBeInTheDocument()
  expect(screen.queryByText('Bob')).not.toBeInTheDocument()

  await user.click(screen.getByRole('combobox', { name: 'Select job' }))
  await user.click(await screen.findByRole('option', { name: 'Job B' }))

  expect(await screen.findByText('Bob')).toBeInTheDocument()
  expect(screen.getByText('Job B feedback')).toBeInTheDocument()
  expect(screen.queryByText('Alice')).not.toBeInTheDocument()
})

test('shows updated label and feedback after the invalidated query refetches', async () => {
  const updatedEvaluation = {
    ...ownEvaluation,
    relevance_label: 2,
    notes: [{
      ...ownEvaluation.notes[0],
      note: 'Latest feedback',
    }],
    updated_at: '2024-01-02T00:00:00Z',
  }

  mockEvaluations([ownEvaluation], [updatedEvaluation])
  ;(apiClient.put as any).mockResolvedValue({ data: updatedEvaluation })
  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))

  const updatedFeedback = await screen.findByText('Latest feedback')
  const row = updatedFeedback.closest('tr')

  expect(row).not.toBeNull()
  expect(within(row!).getByText('2')).toBeInTheDocument()
  expect(apiClient.get).toHaveBeenCalledTimes(4)
})

test.each([
  [409, 'This evaluation changed since it was loaded. Refresh and try again.'],
  [403, 'You are not authorized to edit this evaluation.'],
  [500, 'Unable to save evaluation. Please try again.'],
])('shows an appropriate message for HTTP %i save errors', async (status, message) => {
  mockEvaluations([ownEvaluation])
  mockSaveError(status)
  renderPage()

  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))

  expect(await screen.findByText(message)).toBeInTheDocument()
})
