import { useAuth } from '../features/auth/AuthContext'
import { useQuery } from '@tanstack/react-query'
import { fetchJobs, fetchCandidates, fetchEvaluations, fetchHealth, fetchMatchScoreDistribution } from '../features/dashboard/api'
import Sidebar from '../components/layout/Sidebar'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { ArrowUpRight, BriefcaseBusiness, CircleDashed, Users, Sparkles } from 'lucide-react'

export default function DashboardPage() {
  const { selectedWorkspace } = useAuth()
  const wsId = selectedWorkspace?.workspace_id

  const jobsQ = useQuery({ queryKey: ['jobs', wsId], queryFn: () => fetchJobs(wsId!), enabled: !!wsId })
  const candsQ = useQuery({ queryKey: ['candidates', wsId], queryFn: () => fetchCandidates(wsId!), enabled: !!wsId })
  const evalsQ = useQuery({ queryKey: ['evaluations', wsId], queryFn: () => fetchEvaluations(wsId!), enabled: !!wsId })
  const scoreDistributionQ = useQuery({
    queryKey: ['match-score-distribution', wsId],
    queryFn: () => fetchMatchScoreDistribution(wsId!),
    enabled: !!wsId,
  })
  const healthQ = useQuery({ queryKey: ['health'], queryFn: fetchHealth, staleTime: 30_000 })

  if (!wsId) return <div className="p-6 text-slate-200">Select a workspace.</div>

  const jobs = jobsQ.data ?? []
  const cands = candsQ.data ?? []
  const evals = evalsQ.data ?? []

  const activeJobs = jobs.filter(j => ['OPEN', 'ACTIVE'].includes(String(j.status ?? '').toUpperCase())).length
  const totalCandidates = cands.length
  const pairs = jobs.reduce((total, job) => total + job.candidate_count, 0)
  const reviewed = evals.filter(e => e.review_status === 'reviewed').length
  const pending = evals.filter(e => e.review_status === 'needs_human_review').length

  const perJob = jobs.map(job => ({ job: job.title, count: job.candidate_count }))
  const perJobChartHeight = chartHeight(perJob)

  const evalStatus = [
    { name: 'Reviewed', value: reviewed },
    { name: 'Pending', value: pending },
  ]

  const loading = jobsQ.isLoading || candsQ.isLoading || evalsQ.isLoading || scoreDistributionQ.isLoading
  const error = jobsQ.isError || candsQ.isError || evalsQ.isError || scoreDistributionQ.isError
  const apiStatus = healthQ.isLoading
    ? 'Checking API'
    : healthQ.isError || healthQ.data?.status !== 'ok'
      ? 'API unavailable'
      : 'API online'

  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">Overview</p>
              <h1 className="page-title">Dashboard</h1>
            </div>
            <div className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${
              apiStatus === 'API online'
                ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200'
                : 'border-amber-500/25 bg-amber-500/10 text-amber-200'
            }`}>
              <Sparkles size={16} />
              <span>{apiStatus}</span>
            </div>
          </div>

          {loading && <p className="text-slate-300">Loading...</p>}
          {error && <p className="text-red-300">Failed to load data.</p>}
          {!loading && !error && (
            <>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                <Kpi label="Active Jobs" value={activeJobs} icon={BriefcaseBusiness} accent="from-indigo-500/25 to-indigo-500/5" />
                <Kpi label="Total Candidates" value={totalCandidates} icon={Users} accent="from-cyan-500/25 to-cyan-500/5" />
                <Kpi label="Matches" value={pairs} icon={ArrowUpRight} accent="from-emerald-500/25 to-emerald-500/5" />
                <Kpi label="Reviewed" value={reviewed} icon={CircleDashed} accent="from-violet-500/25 to-violet-500/5" />
                <Kpi label="Pending" value={pending} icon={Sparkles} accent="from-amber-500/25 to-amber-500/5" />
              </div>

              <div className="mt-6 grid gap-4 xl:grid-cols-2">
                <div className="panel p-4 md:p-5">
                  <h2 className="section-title">Candidates per Job</h2>
                  <div className="min-w-0" style={{ height: perJobChartHeight }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={perJob} layout="vertical" margin={{ top: 8, right: 12, left: 2, bottom: 4 }} barCategoryGap={16}>
                        <XAxis type="number" stroke="#94a3b8" tickLine={false} axisLine={false} height={24} />
                        <YAxis dataKey="job" type="category" width={132} interval={0} stroke="#cbd5e1" tickLine={false} axisLine={false} tick={<JobAxisTick />} />
                        <Tooltip cursor={false} contentStyle={{ backgroundColor: '#111827', color: '#e2e8f0', border: '1px solid rgba(148,163,184,0.2)', borderRadius: 12 }} />
                        <Bar dataKey="count" fill="#6366f1" activeBar={{ fill: '#818cf8' }} barSize={18} radius={[0, 8, 8, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="panel p-4 md:p-5">
                  <h2 className="section-title">Evaluation Status</h2>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={evalStatus} dataKey="value" nameKey="name" innerRadius={44} outerRadius={72} paddingAngle={4}>
                          {evalStatus.map((_, i) => <Cell key={i} fill={i === 0 ? '#6366f1' : '#38bdf8'} />)}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: '#111827', border: '1px solid rgba(148,163,184,0.2)', borderRadius: 12 }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div aria-label="Evaluation status legend" className="mt-2 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-300">
                    {evalStatus.map((item, index) => (
                      <div key={item.name} className="flex items-center gap-2">
                        <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${index === 0 ? 'bg-indigo-500' : 'bg-sky-400'}`} />
                        <span>{item.name}: {item.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="panel mt-6 p-4 md:p-5">
                <h2 className="section-title">Match score distribution</h2>
                {scoreDistributionQ.data && (
                  <div className="grid gap-6 xl:grid-cols-2">
                    <ScoreDistributionChart
                      title="Experimental Combined Score Distribution"
                      distribution={scoreDistributionQ.data.experimental_combined_score}
                      note="Experimental weighted score; not a probability of hiring success or an automatic recommendation."
                    />
                    <ScoreDistributionChart
                      title="TF-IDF Similarity Distribution"
                      distribution={scoreDistributionQ.data.tfidf_similarity}
                      note="Persisted cosine similarity displayed on a 0–100 scale."
                    />
                  </div>
                )}
              </div>

              <div className="mt-6 grid gap-4 xl:grid-cols-2">
                <div className="panel p-4 md:p-5">
                  <h2 className="section-title">Recent jobs</h2>
                  <table className="table-shell">
                    <tbody>
                      {jobs.slice(0, 5).map(j => (
                        <tr key={j.job_id}>
                          <td className="font-medium text-slate-100">{j.title}</td>
                          <td className="text-right"><span className="status-pill neutral">{j.status}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {jobs.length === 0 && <p className="text-sm text-slate-400">No jobs.</p>}
                </div>

                <div className="panel p-4 md:p-5">
                  <h2 className="section-title">Recent candidates</h2>
                  <table className="table-shell">
                    <tbody>
                      {cands.slice(0, 5).map(c => (
                        <tr key={c.candidate_id}>
                          <td className="font-medium text-slate-100">{c.full_name}</td>
                          <td className="text-right text-slate-400">{c.current_title ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {cands.length === 0 && <p className="text-sm text-slate-400">No candidates.</p>}
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function ScoreDistributionChart({
  title,
  distribution,
  note,
}: {
  title: string
  distribution: {
    score_scale: string
    total_scored_matches: number
    buckets: { range: string; count: number }[]
  }
  note: string
}) {
  return (
    <section aria-label={title} className="min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
        <span className="text-xs text-slate-400">Total scored matches: {distribution.total_scored_matches}</span>
      </div>
      <p className="mt-1 text-xs text-slate-400">{note}</p>
      {distribution.total_scored_matches === 0 ? (
        <p className="mt-4 rounded-xl border border-slate-700/70 bg-slate-900/50 p-4 text-sm text-slate-300">
          No persisted scores are available yet.
        </p>
      ) : (
        <div className="mt-3 h-56 min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={distribution.buckets} layout="vertical" margin={{ top: 4, right: 12, left: 4, bottom: 4 }}>
              <XAxis type="number" allowDecimals={false} stroke="#94a3b8" tickLine={false} axisLine={false} />
              <YAxis dataKey="range" type="category" width={58} stroke="#cbd5e1" tickLine={false} axisLine={false} />
              <Tooltip
                cursor={false}
                formatter={(value) => [`${value ?? 0} matches`, 'Count']}
                labelFormatter={label => `Score range: ${label}`}
                contentStyle={{ backgroundColor: '#111827', color: '#e2e8f0', border: '1px solid rgba(148,163,184,0.2)', borderRadius: 12 }}
              />
              <Bar dataKey="count" name="Matches" fill="#38bdf8" activeBar={{ fill: '#7dd3fc' }} barSize={20} radius={[0, 8, 8, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}

function Kpi({ label, value, icon: Icon, accent }: { label: string; value: number; icon: any; accent: string }) {
  return (
    <div className="metric-card overflow-hidden">
      <div className={`mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${accent}`}>
        <Icon size={18} className="text-white" />
      </div>
      <span className="metric-label">{label}</span>
      <p className="metric-value">{value}</p>
    </div>
  )
}

function JobAxisTick({ x = 0, y = 0, payload }: { x?: number; y?: number; payload?: { value?: string | number } }) {
  const lines = wrapJobTitle(String(payload?.value ?? ''))
  const startDy = -((lines.length - 1) * 13) / 2
  return (
    <text x={x - 8} y={y} textAnchor="end" fill="#cbd5e1" fontSize={12}>
      {lines.map((line, index) => (
        <tspan key={`${line}-${index}`} x={x - 8} dy={index === 0 ? startDy : 13}>{line}</tspan>
      ))}
    </text>
  )
}

function wrapJobTitle(title: string, maxCharacters = 17): string[] {
  const lines: string[] = []
  for (const word of title.split(/\s+/).filter(Boolean)) {
    let remaining = word
    while (remaining.length > maxCharacters) {
      lines.push(remaining.slice(0, maxCharacters))
      remaining = remaining.slice(maxCharacters)
    }
    const lastLine = lines.at(-1)
    if (lastLine && lastLine.length + remaining.length + 1 <= maxCharacters) {
      lines[lines.length - 1] = `${lastLine} ${remaining}`
    } else if (remaining) {
      lines.push(remaining)
    }
  }
  return lines.length > 0 ? lines : ['']
}

function chartHeight(jobs: Array<{ job: string }>): number {
  const maxLabelLines = jobs.reduce(
    (maximum, item) => Math.max(maximum, wrapJobTitle(item.job).length),
    1,
  )
  return Math.max(300, jobs.length * Math.max(56, maxLabelLines * 13 + 12))
}