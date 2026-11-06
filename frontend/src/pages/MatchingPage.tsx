import axios from 'axios'
import { useState } from 'react'
import { useAuth } from '../features/auth/AuthContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { fetchJobs } from '../features/dashboard/api'
import { fetchMatching, runMatching } from '../features/matching/api'
import { apiClient } from '../services/apiClient'
import Sidebar from '../components/layout/Sidebar'
import StyledSelect from '../components/shared/StyledSelect'
import { SkillChips } from '../components/shared/Primitives'

interface ShortlistRecord {
  candidate_id: string
}

function getErrorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const detail: unknown = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (error.response) return `${fallback} (HTTP ${error.response.status}).`
  }
  return fallback
}

export default function MatchingPage() {
  const { selectedWorkspace } = useAuth()
  const wsId = selectedWorkspace?.workspace_id
  return <MatchingWorkspace key={wsId ?? 'no-workspace'} wsId={wsId} />
}

function MatchingWorkspace({ wsId }: { wsId: string | undefined }) {
  const qc = useQueryClient()
  const jobsQuery = useQuery({ queryKey: ['jobs', wsId], queryFn: () => fetchJobs(wsId!), enabled: !!wsId })
  const jobs = jobsQuery.data
  const [jobId, setJobId] = useState('')
  const [feedback, setFeedback] = useState<{ candidateId: string; message: string; error: boolean } | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  const { data: results, isLoading, isError: matchingQueryIsError, error: matchingQueryError } = useQuery({
    queryKey: ['matching', wsId, jobId],
    queryFn: () => fetchMatching(wsId!, jobId),
    enabled: !!wsId && !!jobId,
  })

  const shortlistsQuery = useQuery({
    queryKey: ['shortlists', wsId, jobId],
    queryFn: async () => (await apiClient.get<ShortlistRecord[]>('/shortlists', {
      params: { workspace_id: wsId, job_id: jobId },
    })).data,
    enabled: !!wsId && !!jobId,
  })

  const runMatchingMutation = useMutation({
    mutationFn: () => runMatching(wsId!, jobId),
    onMutate: () => {
      setRunError(null)
      setFeedback(null)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['matching', wsId, jobId] })
      qc.invalidateQueries({ queryKey: ['shortlists', wsId, jobId] })
    },
    onError: (error) => {
      const detail: unknown =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      setRunError(typeof detail === 'string' ? detail : 'Matching could not be completed.')
    },
  })

  const shortlist = useMutation({
    mutationFn: (variables: { workspaceId: string; jobId: string; candidateId: string }) =>
      apiClient.post('/shortlists', {
        workspace_id: variables.workspaceId,
        job_id: variables.jobId,
        candidate_id: variables.candidateId,
      }),
    onMutate: variables => {
      setFeedback({ candidateId: variables.candidateId, message: '', error: false })
    },
    onSuccess: (response, variables) => {
      setFeedback({
        candidateId: variables.candidateId,
        message: response.status === 200 ? 'This candidate is already shortlisted for this job.' : 'Candidate added to the shortlist.',
        error: false,
      })
      qc.invalidateQueries({ queryKey: ['shortlists', variables.workspaceId, variables.jobId] })
      qc.invalidateQueries({ queryKey: ['shortlists', variables.workspaceId] })
      qc.invalidateQueries({
        queryKey: ['job-candidates', variables.workspaceId, variables.jobId],
      })
    },
    onError: (error, variables) => {
      setFeedback({
        candidateId: variables.candidateId,
        message: getErrorMessage(error, 'Could not add candidate to the shortlist.'),
        error: true,
      })
    },
  })

  const list = results ?? []
  const selectedJob = jobs?.find(job => job.job_id === jobId)
  const shortlistedIds = new Set((shortlistsQuery.data ?? []).map(item => item.candidate_id))
  const canRun = !!wsId && !!jobId && !runMatchingMutation.isPending

  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">Intelligence</p>
              <h1 className="page-title">Matching</h1>
            </div>
            <div className="flex w-full max-w-xl items-center gap-3">
              <StyledSelect
                aria-label="Job"
                value={jobId}
                placeholder="Select job"
                options={(jobs ?? []).map(job => ({ value: job.job_id, label: job.title }))}
                onValueChange={value => {
                  setJobId(value)
                  setFeedback(null)
                  setRunError(null)
                }} />
              <button
                disabled={!canRun}
                onClick={() => runMatchingMutation.mutate()}
                className={`button-primary whitespace-nowrap ${runMatchingMutation.isPending ? 'opacity-70 cursor-not-allowed' : ''}`}
              >
                {runMatchingMutation.isPending ? 'Running matching…' : 'Run Matching'}
              </button>
              {runError && <span className="text-xs text-red-300">{runError}</span>}
            </div>
          </div>

          {jobsQuery.isLoading && <p role="status" className="mb-3 text-sm text-slate-300">Loading workspace jobs...</p>}
          {jobsQuery.isError && <p role="alert" className="mb-3 text-sm text-red-300">{getErrorMessage(jobsQuery.error, 'Failed to load workspace jobs.')}</p>}
          {jobId && selectedJob && (
            <section className="panel mb-5 p-4 md:p-5" aria-label="Selected job requirements">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="section-title">{selectedJob.title}</h2>
                  <p className="mt-1 text-sm text-slate-300">{selectedJob.description || 'No job description available.'}</p>
                </div>
                <span className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300">{selectedJob.status}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate-300">
                <span>Experience: {selectedJob.minimum_experience_years == null ? 'Not specified' : `${selectedJob.minimum_experience_years}+ years`}</span>
                <span>Location: {selectedJob.location || 'Not specified'}</span>
                <span>Employment: {selectedJob.employment_type || 'Not specified'}</span>
              </div>
              <div className="mt-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Required skills</h3>
                <div className="mt-2">
                  <SkillChips skills={selectedJob.required_skills} label="Required skills" />
                </div>
              </div>
            </section>
          )}

          {isLoading && <p className="text-slate-300">Loading...</p>}
          {matchingQueryIsError && jobId && <p role="alert" className="text-red-300">{getErrorMessage(matchingQueryError, 'Failed to load matching results.')}</p>}
          {shortlistsQuery.isError && jobId && <p role="alert" className="mb-3 text-sm text-amber-200">Could not check current shortlist entries. The API still prevents duplicate active entries.</p>}
          {shortlist.isPending && <p className="text-slate-300">Adding candidate to shortlist...</p>}
          {!isLoading && !matchingQueryIsError && jobId && list.length === 0 && <p className="text-slate-300">No stored matching results for this job.</p>}

          {list.length > 0 && (
            <div className="panel overflow-x-auto">
              <table className="table-shell min-w-[1050px]">
                <thead>
                  <tr>
                    <th className="w-48">Candidate</th>
                    <th className="w-40">Title</th>
                    <th className="w-24">TF-IDF</th>
                    <th className="w-28">Skill Coverage</th>
                    <th className="w-28">Combined (Exp)</th>
                    <th className="w-36">Experience</th>
                    <th className="w-36">Location</th>
                    <th className="w-[28rem]">Explanation</th>
                    <th className="w-36">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map(r => {
                    const matchedSkills = r.explanation?.matched_skills ?? []
                    const missingSkills = r.explanation?.missing_skills ?? []
                    return <tr key={r.candidate_id}>
                      <td><Link className="font-medium text-indigo-200 hover:text-white hover:underline" to={`/candidates/${r.candidate_id}`}>{r.candidate_name}</Link></td>
                      <td className="text-slate-300">{r.current_title ?? '—'}</td>
                      <td>{r.tfidf_similarity != null ? Math.round(r.tfidf_similarity * 100) + '%' : '-'}</td>
                      <td>{r.skill_coverage != null ? Math.round(r.skill_coverage * 100) + '%' : '-'}</td>
                      <td>{r.hybrid_score != null ? Math.round(r.hybrid_score) + '%' : '-'}</td>
                      <td className="text-slate-300">{r.experience_compatibility ?? '—'}</td>
                      <td className="text-slate-300">{r.location_compatibility ?? '—'}</td>
                      <td className="whitespace-normal text-xs leading-5 text-slate-300">
                        {matchedSkills.length > 0 && <div><span className="font-semibold text-emerald-200">Matched:</span> {matchedSkills.join(', ')}</div>}
                        {missingSkills.length > 0 && <div><span className="font-semibold text-amber-200">Missing:</span> {missingSkills.join(', ')}</div>}
                        {!matchedSkills.length && !missingSkills.length && <span>Explanation unavailable.</span>}
                      </td>
                      <td>
                        <button
                          onClick={() => {
                            if (wsId && jobId) shortlist.mutate({ workspaceId: wsId, jobId, candidateId: r.candidate_id })
                          }}
                          disabled={!wsId || !jobId || shortlist.isPending || shortlistedIds.has(r.candidate_id)}
                          className="button-secondary whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-70"
                        >
                          {shortlistedIds.has(r.candidate_id) ? 'Shortlisted' : 'Shortlist'}
                        </button>
                        {feedback && feedback.candidateId === r.candidate_id && feedback.message && <p role={feedback.error ? 'alert' : 'status'} className={`mt-2 whitespace-normal text-xs ${feedback.error ? 'text-red-300' : 'text-emerald-300'}`}>{feedback.message}</p>}
                      </td>
                    </tr>
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-4 flex items-center gap-2 text-sm text-slate-400">
            <Sparkles size={14} />
            <span>Explainability is generated from skill coverage and compatibility signals.</span>
          </div>
        </div>
      </main>
    </div>
  )
}