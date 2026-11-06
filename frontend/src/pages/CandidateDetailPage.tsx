import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, PencilLine } from 'lucide-react'
import Sidebar from '../components/layout/Sidebar'
import { useAuth } from '../features/auth/AuthContext'
import { fetchCandidate, fetchJobs } from '../features/dashboard/api'
import { apiClient } from '../services/apiClient'
import StyledSelect from '../components/shared/StyledSelect'
import CandidateEditorDialog from '../components/candidates/CandidateEditorDialog'
import { updateCandidate, type CandidateInput } from '../features/candidates/api'
import { getApiErrorMessage } from '../lib/apiErrors'

interface ShortlistItem {
  candidate_id: string
  job_id: string
  status: string
}

export default function CandidateDetailPage() {
  const { candidateId } = useParams()
  const { selectedWorkspace } = useAuth()
  const workspaceId = selectedWorkspace?.workspace_id
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState('')
  const [shortlistMessage, setShortlistMessage] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

  const candidateQuery = useQuery({
    queryKey: ['candidate', workspaceId, candidateId],
    queryFn: () => fetchCandidate(workspaceId!, candidateId!),
    enabled: !!workspaceId && !!candidateId,
  })
  const jobsQuery = useQuery({
    queryKey: ['jobs', workspaceId],
    queryFn: () => fetchJobs(workspaceId!),
    enabled: !!workspaceId,
  })
  const shortlistsQuery = useQuery({
    queryKey: ['shortlists', workspaceId],
    queryFn: async () => (await apiClient.get<ShortlistItem[]>('/shortlists', {
      params: { workspace_id: workspaceId },
    })).data,
    enabled: !!workspaceId,
  })
  const shortlistMutation = useMutation({
    mutationFn: () => apiClient.post('/shortlists', {
      workspace_id: workspaceId,
      job_id: jobId,
      candidate_id: candidateId,
    }),
    onSuccess: () => {
      setShortlistMessage('Candidate added to the selected job shortlist.')
      queryClient.invalidateQueries({ queryKey: ['shortlists', workspaceId] })
    },
    onError: (error: unknown) => {
      setShortlistMessage(getApiErrorMessage(error, 'Unable to add candidate to the shortlist.'))
    },
  })
  const updateMutation = useMutation({
    mutationFn: (input: CandidateInput) => updateCandidate(workspaceId!, candidateId!, input),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['candidate', workspaceId, candidateId] }),
        queryClient.invalidateQueries({ queryKey: ['candidates', workspaceId] }),
      ])
      setEditing(false)
    },
  })

  const candidate = candidateQuery.data
  const alreadyShortlisted = shortlistsQuery.data?.some(item =>
    item.candidate_id === candidateId && item.job_id === jobId && item.status === 'ACTIVE',
  ) ?? false

  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <div className="page-shell">
          <Link to="/candidates" className="mb-4 inline-flex items-center gap-2 text-sm text-indigo-200 hover:text-white">
            <ArrowLeft size={16} /> Back to candidates
          </Link>
          {candidateQuery.isLoading && <p className="text-slate-300">Loading candidate profile...</p>}
          {candidateQuery.isError && <p role="alert" className="text-red-300">{getApiErrorMessage(candidateQuery.error, 'Failed to load candidate profile.')}</p>}
          {!candidateQuery.isLoading && !candidateQuery.isError && !candidate && (
            <p className="text-slate-300">This candidate is unavailable in the selected workspace.</p>
          )}
          {candidate && (
            <>
              <div className="page-header">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">Candidate profile</p>
                  <h1 className="page-title">{candidate.full_name}</h1>
                  <p className="mt-1 text-slate-300">{candidate.current_title ?? 'Title unavailable'}</p>
                </div>
                <button type="button" className="button-secondary inline-flex items-center justify-center gap-2" onClick={() => setEditing(true)}>
                  <PencilLine size={16} aria-hidden="true" /> Edit profile
                </button>
              </div>

              <section className="panel space-y-5 p-4 md:p-5" aria-label="Candidate information">
                <ProfileField label="Summary" value={candidate.summary || 'Unavailable'} />
                <div className="grid gap-4 sm:grid-cols-2">
                  <ProfileField label="Skills" value={candidate.skills.length ? candidate.skills.map(skill =>
                    skill.years_experience == null ? skill.name : `${skill.name} (${skill.years_experience} years)`,
                  ).join(', ') : 'Unavailable'} />
                  <ProfileField label="Experience" value={candidate.experience_years == null ? 'Unavailable' : `${candidate.experience_years} years`} />
                  <ProfileField label="Location" value={candidate.location ?? 'Unavailable'} />
                  <ProfileField label="Email" value={candidate.email ?? 'Unavailable (not provided by the API)'} />
                </div>
                <div>
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Sources</h2>
                  {candidate.sources.length === 0
                    ? <p className="mt-1 text-sm text-slate-300">Unavailable</p>
                    : (
                      <ul className="mt-2 space-y-3">
                        {candidate.sources.map((source, index) => (
                          <li key={`${source.provider}-${source.source_record_id ?? index}`} className="rounded-xl border border-slate-800 p-3 text-sm text-slate-300">
                            <p>{source.provider}</p>
                            <p>Source record: {source.source_record_id ?? 'Unavailable'}</p>
                            {source.source_url
                              ? <a className="break-all text-indigo-200 hover:underline" href={source.source_url} target="_blank" rel="noreferrer">{source.source_url}</a>
                              : <p>Source URL: Unavailable</p>}
                            <p>Authorized basis: {source.authorized_basis ?? 'Unavailable'}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                </div>
              </section>

              <section className="panel mt-6 p-4 md:p-5" aria-label="Associated jobs and matching results">
                <h2 className="section-title">Associated jobs and matching results</h2>
                {candidate.associated_jobs.length === 0 && <p className="text-slate-300">No associated jobs are available.</p>}
                <ul className="divide-y divide-slate-800">
                  {candidate.associated_jobs.map(association => (
                    <li key={association.job_id} className="py-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <Link className="font-medium text-indigo-200 hover:text-white hover:underline" to={`/jobs/${association.job_id}`}>
                          {association.title}
                        </Link>
                        <span className="text-sm text-slate-400">Stage: {association.stage} · {association.status}</span>
                      </div>
                      {association.matching_results.length === 0
                        ? <p className="mt-1 text-sm text-slate-400">No stored matching result is available.</p>
                        : association.matching_results.map(result => (
                          <p key={`${result.model_name}-${result.model_version}`} className="mt-1 text-sm text-slate-300">
                            {result.model_name} {result.model_version} · TF-IDF {result.tfidf_similarity == null ? 'Unavailable' : `${Math.round(result.tfidf_similarity * 100)}%`}
                          </p>
                        ))}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="panel mt-6 max-w-2xl p-4 md:p-5" aria-label="Add candidate to shortlist">
                <h2 className="section-title">Shortlist for a job</h2>
                {jobsQuery.isLoading && <p className="text-sm text-slate-300">Loading workspace jobs...</p>}
                {jobsQuery.isError && <p role="alert" className="text-sm text-red-300">{getApiErrorMessage(jobsQuery.error, 'Failed to load workspace jobs.')}</p>}
                {!jobsQuery.isLoading && !jobsQuery.isError && (
                  <div className="space-y-3">
                    <label className="block text-sm text-slate-300" htmlFor="candidate-shortlist-job">Select a job in this workspace</label>
                    <StyledSelect
                      id="candidate-shortlist-job"
                      aria-label="Select a job in this workspace"
                      value={jobId}
                      placeholder="Select job"
                      options={(jobsQuery.data ?? []).map(job => ({ value: job.job_id, label: job.title }))}
                      onValueChange={value => {
                      setJobId(value)
                      setShortlistMessage(null)
                    }} />
                    <button
                      type="button"
                      className="button-primary disabled:cursor-not-allowed disabled:opacity-70"
                      disabled={!jobId || shortlistMutation.isPending || alreadyShortlisted || jobsQuery.data?.length === 0}
                      onClick={() => shortlistMutation.mutate()}
                    >
                      {shortlistMutation.isPending ? 'Adding...' : alreadyShortlisted ? 'Already shortlisted' : 'Add to shortlist'}
                    </button>
                    {shortlistsQuery.isError && <p role="alert" className="text-sm text-amber-200">Could not check existing shortlist entries; the API still prevents duplicate active entries.</p>}
                    {shortlistMessage && <p role={shortlistMutation.isError ? 'alert' : 'status'} className={`text-sm ${shortlistMutation.isError ? 'text-red-300' : 'text-emerald-300'}`}>{shortlistMessage}</p>}
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </main>
      <CandidateEditorDialog
        open={editing}
        candidate={candidate}
        title="Edit candidate profile"
        pending={updateMutation.isPending}
        error={updateMutation.error}
        onClose={() => {
          if (updateMutation.isPending) return
          setEditing(false)
          updateMutation.reset()
        }}
        onSubmit={input => updateMutation.mutate(input)}
      />
    </div>
  )
}

function ProfileField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</h2>
      <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-100">{value}</p>
    </div>
  )
}
