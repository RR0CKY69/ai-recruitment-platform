import { beforeEach, expect, test, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const chartState = vi.hoisted(() => ({
  barData: [] as Array<{ job: string; count: number }>,
  barDataSets: [] as Array<Array<{ job?: string; range?: string; count: number }>>,
  yAxisProps: {} as Record<string, unknown>,
  yAxisPropsList: [] as Array<Record<string, unknown>>,
  barProps: {} as Record<string, unknown>,
  barPropsList: [] as Array<Record<string, unknown>>,
  tooltipCursors: [] as unknown[],
  tooltipProps: [] as Array<Record<string, unknown>>,
  barChartProps: {} as Record<string, unknown>,
  responsiveProps: [] as Array<Record<string, unknown>>,
}))

vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({ selectedWorkspace: { workspace_id: 'workspace-1' } }),
}))
vi.mock('../components/layout/Sidebar', () => ({ default: () => null }))
vi.mock('../features/dashboard/api', () => ({
  fetchJobs: vi.fn(),
  fetchCandidates: vi.fn(),
  fetchEvaluations: vi.fn(),
  fetchHealth: vi.fn(),
  fetchMatchScoreDistribution: vi.fn(),
}))
vi.mock('recharts', () => ({
  BarChart: ({ data, children, ...props }: { data: Array<{ job: string; count: number }>; children: React.ReactNode; [key: string]: unknown }) => {
    chartState.barData = data
    chartState.barDataSets.push(data)
    chartState.barChartProps = props
    return children
  },
  Bar: (props: Record<string, unknown>) => {
    chartState.barProps = props
    chartState.barPropsList.push(props)
    return null
  },
  XAxis: () => null,
  YAxis: (props: Record<string, unknown>) => {
    chartState.yAxisProps = props
    chartState.yAxisPropsList.push(props)
    return null
  },
  Tooltip: (props: { cursor?: unknown; formatter?: unknown; labelFormatter?: unknown }) => {
    chartState.tooltipCursors.push(props.cursor)
    chartState.tooltipProps.push(props)
    return null
  },
  ResponsiveContainer: ({ children, ...props }: { children: React.ReactNode; [key: string]: unknown }) => {
    chartState.responsiveProps.push(props)
    return children
  },
  PieChart: ({ children }: { children: React.ReactNode }) => children,
  Pie: () => null,
  Cell: () => null,
}))

import { fetchCandidates, fetchEvaluations, fetchHealth, fetchJobs, fetchMatchScoreDistribution } from '../features/dashboard/api'
import DashboardPage from './DashboardPage'

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><DashboardPage /></QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  chartState.barData = []
  chartState.barDataSets = []
  chartState.yAxisProps = {}
  chartState.yAxisPropsList = []
  chartState.barProps = {}
  chartState.barPropsList = []
  chartState.tooltipCursors = []
  chartState.tooltipProps = []
  chartState.barChartProps = {}
  chartState.responsiveProps = []
})

const scoreDistribution = {
  experimental_combined_score: {
    score_scale: '0–100 experimental combined score',
    total_scored_matches: 15,
    buckets: [
      { range: '0–20', count: 1 },
      { range: '21–40', count: 2 },
      { range: '41–60', count: 3 },
      { range: '61–80', count: 4 },
      { range: '81–100', count: 5 },
    ],
  },
  tfidf_similarity: {
    score_scale: '0–100 scale (cosine similarity × 100)',
    total_scored_matches: 10,
    buckets: [
      { range: '0–20', count: 0 },
      { range: '21–40', count: 1 },
      { range: '41–60', count: 2 },
      { range: '61–80', count: 3 },
      { range: '81–100', count: 4 },
    ],
  },
}

test('shows dashboard KPIs, readable evaluation labels, and transparent bar hover cursor', async () => {
  vi.mocked(fetchJobs).mockResolvedValue([
    { job_id: 'j1', title: 'Senior Platform Reliability Engineer', status: 'OPEN', location: 'Remote', description: '', required_skills: [], minimum_experience_years: null, employment_type: null, candidate_count: 7 },
    { job_id: 'j2', title: 'Closed role', status: 'CLOSED', description: '', required_skills: [], minimum_experience_years: null, employment_type: null, candidate_count: 0 },
    { job_id: 'j3', title: 'Machine Learning Engineer', status: 'CLOSED', description: '', required_skills: [], minimum_experience_years: null, employment_type: null, candidate_count: 0 },
    { job_id: 'j4', title: 'Senior Accountant', status: 'CLOSED', description: '', required_skills: [], minimum_experience_years: null, employment_type: null, candidate_count: 0 },
    { job_id: 'j5', title: 'Construction Project Coordinator', status: 'CLOSED', description: '', required_skills: [], minimum_experience_years: null, employment_type: null, candidate_count: 0 },
  ])
  vi.mocked(fetchCandidates).mockResolvedValue([
    { candidate_id: 'c1', full_name: 'Candidate One', summary: '', experience_years: null, skills: [], sources: [] },
    { candidate_id: 'c2', full_name: 'Candidate Two', summary: '', experience_years: null, skills: [], sources: [] },
  ])
  vi.mocked(fetchEvaluations).mockResolvedValue([
    { job_id: 'j1', candidate_id: 'c1', review_status: 'reviewed', relevance_label: 2 },
    { job_id: 'j1', candidate_id: 'c2', review_status: 'needs_human_review', relevance_label: null },
  ])
  vi.mocked(fetchHealth).mockResolvedValue({ status: 'ok' })
  vi.mocked(fetchMatchScoreDistribution).mockResolvedValue(scoreDistribution)

  renderDashboard()

  await waitFor(() => expect(screen.getByText('Active Jobs')).toBeInTheDocument())
  expect(screen.getByText('API online')).toBeInTheDocument()
  expect(screen.queryByText('AI pipeline healthy')).not.toBeInTheDocument()
  expect(Array.from(document.querySelectorAll('.metric-value')).map(node => node.textContent)).toEqual([
    '1', '2', '7', '1', '1',
  ])
  expect(screen.getByText('Reviewed: 1')).toBeInTheDocument()
  expect(screen.getByText('Pending: 1')).toBeInTheDocument()
  expect(chartState.barDataSets).toContainEqual([
    { job: 'Senior Platform Reliability Engineer', count: 7 },
    { job: 'Closed role', count: 0 },
    { job: 'Machine Learning Engineer', count: 0 },
    { job: 'Senior Accountant', count: 0 },
    { job: 'Construction Project Coordinator', count: 0 },
  ])
  const jobsAxis = chartState.yAxisPropsList.find(props => props.dataKey === 'job')
  expect(jobsAxis).toMatchObject({ dataKey: 'job', type: 'category', interval: 0 })
  if (!jobsAxis) throw new Error('Candidates per job axis was not rendered.')
  expect((jobsAxis.tick as React.ReactElement).type).toBeDefined()
  expect(chartState.tooltipCursors).toContain(false)
  const scoreTooltip = chartState.tooltipProps.find(props => typeof props.labelFormatter === 'function')
  if (!scoreTooltip) throw new Error('Score distribution tooltip was not rendered.')
  expect((scoreTooltip.labelFormatter as (label: string) => string)('0–20')).toBe('Score range: 0–20')
  expect((scoreTooltip.formatter as (value: number) => [string, string])(2)).toEqual(['2 matches', 'Count'])
  expect(chartState.barPropsList).toContainEqual(expect.objectContaining({ activeBar: { fill: '#818cf8' } }))
  expect(chartState.barChartProps).toMatchObject({ layout: 'vertical' })
  expect(chartState.responsiveProps).toContainEqual({ width: '100%', height: '100%' })
  expect(document.querySelector('.overflow-x-auto')).not.toBeInTheDocument()
  expect(chartState.barDataSets).toContainEqual(scoreDistribution.experimental_combined_score.buckets)
  expect(chartState.barDataSets).toContainEqual(scoreDistribution.tfidf_similarity.buckets)
  expect(screen.getByText('Experimental Combined Score Distribution')).toBeInTheDocument()
  expect(screen.getByText('TF-IDF Similarity Distribution')).toBeInTheDocument()
  expect(screen.getByText('Total scored matches: 15')).toBeInTheDocument()
  expect(screen.getByText('Total scored matches: 10')).toBeInTheDocument()
  expect(screen.getByText(/not a probability of hiring success/)).toBeInTheDocument()
})

test('shows API data loading and failure states', async () => {
  let resolveJobs!: (jobs: Awaited<ReturnType<typeof fetchJobs>>) => void
  vi.mocked(fetchJobs).mockReturnValueOnce(new Promise(resolve => { resolveJobs = resolve }))
  vi.mocked(fetchCandidates).mockResolvedValueOnce([])
  vi.mocked(fetchEvaluations).mockResolvedValueOnce([])
  vi.mocked(fetchHealth).mockResolvedValue({ status: 'ok' })
  vi.mocked(fetchMatchScoreDistribution).mockResolvedValue(scoreDistribution)
  const view = renderDashboard()
  expect(screen.getByText('Loading...')).toBeInTheDocument()
  resolveJobs([])
  await waitFor(() => expect(screen.getByText('No jobs.')).toBeInTheDocument())

  vi.mocked(fetchJobs).mockRejectedValueOnce(new Error('API unavailable'))
  vi.mocked(fetchCandidates).mockResolvedValueOnce([])
  vi.mocked(fetchEvaluations).mockResolvedValueOnce([])
  vi.mocked(fetchHealth).mockResolvedValue({ status: 'ok' })
  vi.mocked(fetchMatchScoreDistribution).mockResolvedValue(scoreDistribution)
  view.unmount()
  renderDashboard()
  await waitFor(() => expect(screen.getByText('Failed to load data.')).toBeInTheDocument())
})

test('shows empty states when the API has no persisted match scores', async () => {
  vi.mocked(fetchJobs).mockResolvedValue([])
  vi.mocked(fetchCandidates).mockResolvedValue([])
  vi.mocked(fetchEvaluations).mockResolvedValue([])
  vi.mocked(fetchHealth).mockResolvedValue({ status: 'ok' })
  vi.mocked(fetchMatchScoreDistribution).mockResolvedValue({
    experimental_combined_score: {
      score_scale: '0–100 experimental combined score',
      total_scored_matches: 0,
      buckets: scoreDistribution.experimental_combined_score.buckets.map(bucket => ({ ...bucket, count: 0 })),
    },
    tfidf_similarity: {
      score_scale: '0–100 scale (cosine similarity × 100)',
      total_scored_matches: 0,
      buckets: scoreDistribution.tfidf_similarity.buckets.map(bucket => ({ ...bucket, count: 0 })),
    },
  })

  renderDashboard()

  expect(await screen.findAllByText('No persisted scores are available yet.')).toHaveLength(2)
  expect(fetchMatchScoreDistribution).toHaveBeenCalledWith('workspace-1')
})

test('reports match-score API failures', async () => {
  vi.mocked(fetchJobs).mockResolvedValue([])
  vi.mocked(fetchCandidates).mockResolvedValue([])
  vi.mocked(fetchEvaluations).mockResolvedValue([])
  vi.mocked(fetchHealth).mockResolvedValue({ status: 'ok' })
  vi.mocked(fetchMatchScoreDistribution).mockRejectedValue(new Error('API unavailable'))

  renderDashboard()

  expect(await screen.findByText('Failed to load data.')).toBeInTheDocument()
})
