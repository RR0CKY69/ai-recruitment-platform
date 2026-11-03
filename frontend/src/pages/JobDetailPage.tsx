import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import Sidebar from '../components/layout/Sidebar'
import { useAuth } from '../features/auth/AuthContext'
import { fetchJobs } from '../features/dashboard/api'
import { fetchMatching } from '../features/matching/api'

export default function JobDetailPage() {
  const { jobId } = useParams()
  const { selectedWorkspace } = useAuth()
  const workspaceId = selectedWorkspace?.workspace_id
  const jobsQuery = useQuery({
    queryKey: ['jobs', workspaceId],
    queryFn: () => fetchJobs(workspaceId!),
    enabled: !!workspaceId,
  })
  const job = jobsQuery.data?.find(item => item.job_id === jobId)
  const matchingQuery = useQuery({
    queryKey: ['matching', workspaceId, jobId],
    queryFn: () => fetchMatching(workspaceId!, jobId!),
    enabled: !!workspaceId && !!job,
  })

  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <div className="page-shell">
          <Link to="/jobs" className="mb-4 inline-flex items-center gap-2 text-sm text-indigo-200 hover:text-white">
            <ArrowLeft size={16} /> Back to jobs
          </Link>
          {jobsQuery.isLoading && <p className="text-slate-300">Loading job details...</p>}
          {jobsQuery.isError && <p role="alert" className="text-red-300">Failed to load job details.</p>}
          {!jobsQuery.isLoading && !jobsQuery.isError && !job && <p className="text-slate-300">This job is unavailable in the selected workspace.</p>}
          {job && (
            <>
              <div className="page-header">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">Job details</p>
                  <h1 className="page-title">{job.title}</h1>
                </div>
                <span className="status-pill neutral">{job.status}</span>
              </div>

              <section className="panel space-y-5 p-4 md:p-5" aria-label="Job information">
                <div>
                  <h2 className="section-title">Description</h2>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-slate-300">{job.description || 'Unavailable'}</p>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Detail label="Required skills" value={job.required_skills.length ? job.required_skills.join(', ') : 'Unavailable'} />
                  <Detail label="Minimum experience" value={job.minimum_experience_years == null ? 'Unavailable' : `${job.minimum_experience_years} years`} />
                  <Detail label="Location" value={job.location ?? 'Unavailable'} />
                  <Detail label="Employment type" value={job.employment_type ?? 'Unavailable'} />
                  <Detail label="Matched candidates" value={String(job.candidate_count)} />
                </div>
              </section>

              <section className="panel mt-6 p-4 md:p-5" aria-label="Stored matching results">
                <h2 className="section-title">Stored matching results</h2>
                <p className="mb-3 text-xs text-slate-400">The API exposes the current stored result snapshot, not dated run history.</p>
                {matchingQuery.isLoading && <p className="text-slate-300">Loading matching results...</p>}
                {matchingQuery.isError && <p role="alert" className="text-red-300">Failed to load matching results.</p>}
                {!matchingQuery.isLoading && !matchingQuery.isError && (matchingQuery.data?.length ?? 0) === 0 && (
                  <p className="text-slate-300">No stored matching results are available.</p>
                )}
                {!!matchingQuery.data?.length && (
                  <ul className="divide-y divide-slate-800">
                    {matchingQuery.data.map(result => (
                      <li key={result.candidate_id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                        <Link className="font-medium text-indigo-200 hover:text-white hover:underline" to={`/candidates/${result.candidate_id}`}>
                          {result.candidate_name}
                        </Link>
                        <span className="text-sm text-slate-300">
                          TF-IDF {result.tfidf_similarity == null ? 'Unavailable' : `${Math.round(result.tfidf_similarity * 100)}%`}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</h3>
      <p className="mt-1 text-sm text-slate-100">{value}</p>
    </div>
  )
}
