import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ArrowLeft, PencilLine, Plus, UserPlus } from 'lucide-react'
import Sidebar from '../components/layout/Sidebar'
import { useAuth } from '../features/auth/AuthContext'
import { fetchCandidates, fetchJobs, type Candidate } from '../features/dashboard/api'
import { fetchMatching } from '../features/matching/api'
import { ScoreDisplay, StatusBadge, SkillChips } from '../components/shared/Primitives'
import { JobEditorDialog } from './JobsPage'
import CandidateEditorDialog from '../components/candidates/CandidateEditorDialog'
import ConfirmationDialog from '../components/shared/ConfirmationDialog'
import ModalDialog from '../components/shared/ModalDialog'
import SearchField from '../components/shared/SearchField'
import { getApiErrorMessage } from '../lib/apiErrors'
import { updateJob, type JobInput } from '../features/jobs/api'
import {
  assignCandidateToJob,
  fetchJobCandidates,
  removeCandidateFromJob,
} from '../features/assignments/api'
import { createCandidate, type CandidateInput } from '../features/candidates/api'

class CandidateAssignmentError extends Error {
  readonly candidate: Candidate

  constructor(message: string, candidate: Candidate) {
    super(message)
    this.candidate = candidate
  }
}

export default function JobDetailPage() {
  const { jobId } = useParams()
  const { selectedWorkspace } = useAuth()
  const workspaceId = selectedWorkspace?.workspace_id
  const queryClient = useQueryClient()
  const [editingJob, setEditingJob] = useState(false)
  const [assignmentDialog, setAssignmentDialog] = useState(false)
  const [assignmentSearch, setAssignmentSearch] = useState('')
  const [candidateDialog, setCandidateDialog] = useState(false)
  const [removingCandidate, setRemovingCandidate] = useState<{ id: string; name: string } | null>(null)
  const [unassignedCreatedCandidate, setUnassignedCreatedCandidate] = useState<{
    candidate: Candidate
    message: string
  } | null>(null)
  const jobsQuery = useQuery({
    queryKey: ['jobs', workspaceId],
    queryFn: () => fetchJobs(workspaceId!),
    enabled: !!workspaceId,
  })
  const job = jobsQuery.data?.find(item => item.job_id === jobId)
  const candidatesQuery = useQuery({
    queryKey: ['candidates', workspaceId],
    queryFn: () => fetchCandidates(workspaceId!),
    enabled: !!workspaceId && !!job,
  })
  const assignedQuery = useQuery({
    queryKey: ['job-candidates', workspaceId, jobId],
    queryFn: () => fetchJobCandidates(workspaceId!, jobId!),
    enabled: !!workspaceId && !!jobId && !!job,
  })
  const updateJobMutation = useMutation({
    mutationFn: (input: JobInput) => updateJob(workspaceId!, jobId!, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['jobs', workspaceId] })
      setEditingJob(false)
    },
  })
  const assignMutation = useMutation({
    mutationFn: (candidateId: string) => assignCandidateToJob(jobId!, {
      workspace_id: workspaceId!,
      candidate_id: candidateId,
    }),
    onSuccess: async () => {
      setUnassignedCreatedCandidate(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['job-candidates', workspaceId, jobId] }),
        queryClient.invalidateQueries({ queryKey: ['jobs', workspaceId] }),
        queryClient.invalidateQueries({ queryKey: ['candidate', workspaceId] }),
      ])
      setAssignmentDialog(false)
    },
  })
  const removeMutation = useMutation({
    mutationFn: (candidateId: string) => removeCandidateFromJob(workspaceId!, jobId!, candidateId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['job-candidates', workspaceId, jobId] }),
        queryClient.invalidateQueries({ queryKey: ['jobs', workspaceId] }),
        queryClient.invalidateQueries({ queryKey: ['candidate', workspaceId] }),
      ])
      setRemovingCandidate(null)
    },
    onError: () => setRemovingCandidate(null),
  })
  const createAndAssignMutation = useMutation({
    mutationFn: async (input: CandidateInput) => {
      const candidate = await createCandidate({ ...input, workspace_id: workspaceId! })
      try {
        await assignCandidateToJob(jobId!, {
          workspace_id: workspaceId!,
          candidate_id: candidate.candidate_id,
        })
      } catch (error) {
        throw new CandidateAssignmentError(
          `Candidate profile was created, but assignment failed: ${getApiErrorMessage(error, 'unable to assign the candidate')}`,
          candidate,
        )
      }
      return candidate
    },
    onSuccess: async () => {
      setUnassignedCreatedCandidate(null)
      setCandidateDialog(false)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['job-candidates', workspaceId, jobId] }),
        queryClient.invalidateQueries({ queryKey: ['jobs', workspaceId] }),
        queryClient.invalidateQueries({ queryKey: ['candidates', workspaceId] }),
      ])
    },
    onError: async error => {
      if (error instanceof CandidateAssignmentError) {
        setUnassignedCreatedCandidate({ candidate: error.candidate, message: error.message })
        setCandidateDialog(false)
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['candidates', workspaceId] }),
        queryClient.invalidateQueries({ queryKey: ['job-candidates', workspaceId, jobId] }),
      ])
    },
  })
  const matchingQuery = useQuery({
    queryKey: ['matching', workspaceId, jobId],
    queryFn: () => fetchMatching(workspaceId!, jobId!),
    enabled: !!workspaceId && !!job,
  })
  const assignedIds = new Set((assignedQuery.data ?? []).map(candidate => candidate.candidate_id))
  const availableCandidates = (candidatesQuery.data ?? []).filter(candidate => {
    const searchText = [
      candidate.full_name,
      candidate.current_title ?? '',
      candidate.location ?? '',
      candidate.email ?? '',
      ...candidate.skills.map(skill => skill.name),
    ].join(' ').toLocaleLowerCase()
    return !assignedIds.has(candidate.candidate_id) && searchText.includes(assignmentSearch.trim().toLocaleLowerCase())
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
          {jobsQuery.isError && <p role="alert" className="text-red-300">{getApiErrorMessage(jobsQuery.error, 'Failed to load job details.')}</p>}
          {!jobsQuery.isLoading && !jobsQuery.isError && !job && <p className="text-slate-300">This job is unavailable in the selected workspace.</p>}
          {job && (
            <>
              <div className="page-header">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">Job details</p>
                  <h1 className="page-title">{job.title}</h1>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge label={job.status.replace('_', ' ')} />
                  <button type="button" className="button-secondary inline-flex items-center gap-2" onClick={() => setEditingJob(true)}>
                    <PencilLine size={15} aria-hidden="true" /> Edit job
                  </button>
                </div>
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
                  <Detail label="Assigned candidates" value={String(job.candidate_count)} />
                </div>
              </section>

              <section className="panel mt-6 p-4 md:p-5" aria-label="Assigned candidates">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="section-title">Assigned candidates</h2>
                    <p className="text-sm text-slate-400">Only candidates explicitly assigned to this job appear here.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className="button-secondary inline-flex items-center gap-2" onClick={() => setAssignmentDialog(true)}>
                      <Plus size={15} aria-hidden="true" /> Add existing candidate
                    </button>
                    <button type="button" className="button-primary inline-flex items-center gap-2" onClick={() => setCandidateDialog(true)}>
                      <UserPlus size={15} aria-hidden="true" /> Create and assign
                    </button>
                  </div>
                </div>
                {assignedQuery.isLoading && <p role="status" className="text-sm text-slate-300">Loading assigned candidates...</p>}
                {assignedQuery.isError && <p role="alert" className="text-sm text-red-300">{getApiErrorMessage(assignedQuery.error, 'Failed to load job assignments. The assignment API is not currently available.')}</p>}
                {!assignedQuery.isLoading && !assignedQuery.isError && (assignedQuery.data?.length ?? 0) === 0 && (
                  <p className="rounded-xl border border-dashed border-slate-700 px-4 py-6 text-center text-sm text-slate-400">No candidates have been assigned to this job.</p>
                )}
                {!!assignedQuery.data?.length && (
                  <ul className="grid gap-3 md:grid-cols-2">
                    {assignedQuery.data.map(candidate => (
                      <li key={candidate.candidate_id} className="min-w-0 rounded-2xl border border-slate-700/80 bg-slate-900/40 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <Link className="break-words font-semibold text-indigo-100 hover:text-white hover:underline" to={`/candidates/${candidate.candidate_id}`}>
                              {candidate.full_name}
                            </Link>
                            <p className="mt-1 break-words text-sm text-slate-300">{candidate.current_title ?? 'Title unavailable'}</p>
                          </div>
                          <span className="shrink-0 rounded-full bg-cyan-400/10 px-2.5 py-1 text-xs text-cyan-100">Stage: {candidate.stage}</span>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                          <span>{candidate.experience_years == null ? 'Experience unavailable' : `${candidate.experience_years} years`}</span>
                          <span>{candidate.location ?? 'Location unavailable'}</span>
                        </div>
                        <div className="mt-3"><SkillChips skills={candidate.skills.map(skill => skill.name)} /></div>
                        <button
                          type="button"
                          className="mt-4 rounded-lg px-2 py-1 text-xs text-rose-200 hover:bg-rose-500/10"
                          onClick={() => {
                            removeMutation.reset()
                            setRemovingCandidate({ id: candidate.candidate_id, name: candidate.full_name })
                          }}
                        >
                          Remove from job
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {!!assignMutation.error && <p role="alert" className="mt-3 text-sm text-red-300">{getApiErrorMessage(assignMutation.error, 'Unable to assign this candidate.')}</p>}
                {!!removeMutation.error && <p role="alert" className="mt-3 text-sm text-red-300">{getApiErrorMessage(removeMutation.error, 'Unable to remove the job assignment.')}</p>}
                {unassignedCreatedCandidate && (
                  <p role="alert" className="mt-3 text-sm text-amber-200">
                    {unassignedCreatedCandidate.message} The profile remains in the workspace without this job assignment.{' '}
                    <Link className="underline" to={`/candidates/${unassignedCreatedCandidate.candidate.candidate_id}`}>View {unassignedCreatedCandidate.candidate.full_name}</Link>
                  </p>
                )}
              </section>

              <section className="panel mt-6 p-4 md:p-5" aria-label="Stored matching results">
                <h2 className="section-title">Stored matching results</h2>
                <p className="mb-3 text-xs text-slate-400">The API exposes the current stored result snapshot, not dated run history.</p>
                {matchingQuery.isLoading && <p className="text-slate-300">Loading matching results...</p>}
                {matchingQuery.isError && <p role="alert" className="text-red-300">{getApiErrorMessage(matchingQuery.error, 'Failed to load matching results.')}</p>}
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
                          <ScoreDisplay score={result.tfidf_similarity} max={1} label="TF-IDF" />
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
      {job && (
        <JobEditorDialog
          open={editingJob}
          job={job}
          pending={updateJobMutation.isPending}
          error={updateJobMutation.error}
          onClose={() => {
            if (updateJobMutation.isPending) return
            setEditingJob(false)
            updateJobMutation.reset()
          }}
          onSubmit={input => updateJobMutation.mutate(input)}
        />
      )}
      <ModalDialog open={assignmentDialog} title="Add an existing candidate" description="Only profiles from the currently selected workspace are available." onClose={() => {
        if (!assignMutation.isPending) setAssignmentDialog(false)
      }}>
        <div className="space-y-4">
          <SearchField label="Search candidates to assign" placeholder="Search name, title, location or skills" value={assignmentSearch} onChange={setAssignmentSearch} />
          {candidatesQuery.isLoading && <p role="status" className="text-sm text-slate-300">Loading workspace candidates...</p>}
          {candidatesQuery.isError && <p role="alert" className="text-sm text-red-300">{getApiErrorMessage(candidatesQuery.error, 'Failed to load workspace candidates.')}</p>}
          {assignedQuery.isError && <p role="alert" className="text-sm text-amber-200">Assignments could not be loaded, so adding candidates is disabled to prevent duplicates.</p>}
          {!candidatesQuery.isLoading && !candidatesQuery.isError && !assignedQuery.isLoading && !assignedQuery.isError && availableCandidates.length === 0 && (
            <p className="rounded-xl border border-dashed border-slate-700 px-4 py-6 text-center text-sm text-slate-400">
              {(candidatesQuery.data?.length ?? 0) === 0 ? 'No workspace candidates are available.' : 'No unassigned candidates match this search.'}
            </p>
          )}
          {availableCandidates.length > 0 && (
            <ul className="max-h-[55vh] space-y-3 overflow-y-auto pr-1">
              {availableCandidates.map(candidate => (
                <li key={candidate.candidate_id} className="rounded-xl border border-slate-700 bg-slate-900/40 p-3">
                  <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Link className="font-semibold text-indigo-100 hover:underline" to={`/candidates/${candidate.candidate_id}`} onClick={() => setAssignmentDialog(false)}>
                        {candidate.full_name}
                      </Link>
                      <p className="mt-1 text-sm text-slate-300">{candidate.current_title ?? 'Title unavailable'}</p>
                      <p className="mt-1 text-xs text-slate-400">
                        {candidate.experience_years == null ? 'Experience unavailable' : `${candidate.experience_years} years`} · {candidate.location ?? 'Location unavailable'}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="button-secondary shrink-0"
                      disabled={assignMutation.isPending || assignedQuery.isError || assignedIds.has(candidate.candidate_id)}
                      onClick={() => assignMutation.mutate(candidate.candidate_id)}
                    >
                      {assignMutation.isPending ? 'Adding...' : 'Assign'}
                    </button>
                  </div>
                  <div className="mt-3"><SkillChips skills={candidate.skills.map(skill => skill.name)} /></div>
                </li>
              ))}
            </ul>
          )}
          {!!assignMutation.error && <p role="alert" className="text-sm text-red-300">{getApiErrorMessage(assignMutation.error, 'Unable to assign this candidate.')}</p>}
        </div>
      </ModalDialog>
      <CandidateEditorDialog
        open={candidateDialog}
        title="Create and assign candidate"
        pending={createAndAssignMutation.isPending}
        error={createAndAssignMutation.error}
        onClose={() => {
          if (createAndAssignMutation.isPending) return
          setCandidateDialog(false)
          createAndAssignMutation.reset()
        }}
        onSubmit={input => createAndAssignMutation.mutate(input)}
      />
      <ConfirmationDialog
        open={!!removingCandidate}
        title="Remove candidate from this job?"
        description={`${removingCandidate?.name ?? 'This candidate'} will be removed from this job only. Their workspace profile will remain.`}
        confirmLabel="Remove assignment"
        confirmingLabel="Removing..."
        confirming={removeMutation.isPending}
        onCancel={() => setRemovingCandidate(null)}
        onConfirm={() => {
          if (removingCandidate) removeMutation.mutate(removingCandidate.id)
        }}
      />
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
