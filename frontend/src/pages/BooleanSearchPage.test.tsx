import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchJobs: vi.fn(),
  selectedWorkspace: { workspace_id: 'workspace-1' },
}))

vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({ selectedWorkspace: mocks.selectedWorkspace }),
}))
vi.mock('../features/dashboard/api', () => ({ fetchJobs: mocks.fetchJobs }))
vi.mock('../components/layout/Sidebar', () => ({ default: () => null }))

import BooleanSearchPage from './BooleanSearchPage'

const workspaceJobs = [{
  job_id: 'job-1',
  title: 'Python Developer',
  status: 'OPEN',
  description: 'Build APIs for a recruiting platform.',
  required_skills: ['Django', 'FastAPI'],
  minimum_experience_years: 3,
  employment_type: 'Full-time',
  candidate_count: 0,
}]

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <BooleanSearchPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.selectedWorkspace = { workspace_id: 'workspace-1' }
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  })
})

test('loads jobs for the selected workspace and builds editable template queries from the selected job', async () => {
  const user = userEvent.setup()
  mocks.fetchJobs.mockResolvedValue(workspaceJobs)
  renderPage()

  expect(await screen.findByText('Select a job to review its details and generate a Boolean query.')).toBeInTheDocument()
  expect(mocks.fetchJobs).toHaveBeenCalledWith('workspace-1')

  await user.click(screen.getByRole('combobox', { name: 'Workspace job' }))
  await user.click(await screen.findByRole('option', { name: 'Python Developer' }))
  expect(await screen.findByText('Build APIs for a recruiting platform.')).toBeInTheDocument()
  const query = screen.getByRole('textbox', { name: 'Editable Boolean query' })
  await waitFor(() => expect(query).toHaveValue('("Python Developer" AND (Django OR FastAPI))'))

  fireEvent.change(screen.getByLabelText('Include keywords'), { target: { value: 'PostgreSQL Database' } })
  expect(query).toHaveValue('("Python Developer" AND (Django OR FastAPI OR "PostgreSQL Database"))')
  await user.click(screen.getByRole('combobox', { name: 'Included keyword logic' }))
  await user.click(screen.getByRole('option', { name: 'Match all (AND)' }))
  expect(query).toHaveValue('("Python Developer" AND (Django AND FastAPI AND "PostgreSQL Database"))')
  fireEvent.change(screen.getByLabelText('Exclude keywords'), { target: { value: 'Intern' } })
  expect(query).toHaveValue('("Python Developer" AND (Django AND FastAPI AND "PostgreSQL Database") NOT (Intern))')

  fireEvent.change(query, { target: { value: 'custom Boolean query' } })
  expect(query).toHaveValue('custom Boolean query')
  await user.click(screen.getByRole('combobox', { name: 'Query template' }))
  await user.click(screen.getByRole('option', { name: 'Google / X-ray' }))
  expect(query).toHaveValue(
    'site:linkedin.com/in/ "Python Developer" AND (Django AND FastAPI AND "PostgreSQL Database") NOT (Intern)',
  )
})

test('copies the current edited query and makes no external sourcing claim', async () => {
  const user = userEvent.setup()
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  })
  mocks.fetchJobs.mockResolvedValue(workspaceJobs)
  renderPage()
  await user.click(await screen.findByRole('combobox', { name: 'Workspace job' }))
  await user.click(await screen.findByRole('option', { name: 'Python Developer' }))
  const query = await screen.findByRole('textbox', { name: 'Editable Boolean query' })
  fireEvent.change(query, { target: { value: 'edited query' } })
  fireEvent.click(screen.getByRole('button', { name: 'Copy Query' }))

  await waitFor(() => expect(writeText).toHaveBeenCalledWith('edited query'))
  expect(await screen.findByRole('status')).toHaveTextContent('Query copied to clipboard.')
  expect(screen.getByText(/does not search LinkedIn/)).toBeInTheDocument()
})

test('reports job loading errors', async () => {
  mocks.fetchJobs.mockRejectedValue(new Error('workspace API failed'))
  renderPage()
  expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load workspace jobs.')
})
