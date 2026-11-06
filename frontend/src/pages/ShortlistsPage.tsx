import axios from 'axios'
import { useState } from 'react'
import { useAuth } from '../features/auth/AuthContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { apiClient } from '../services/apiClient'
import { fetchJobs } from '../features/dashboard/api'
import { fetchJobCandidates } from '../features/assignments/api'
import Sidebar from '../components/layout/Sidebar'
import StyledSelect from '../components/shared/StyledSelect'

interface Shortlist {
  shortlist_id: string
  job_id: string
  candidate_id: string
  job_title: string
  candidate_name: string
  current_title?: string
  status: string
}

function getErrorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const detail: unknown = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (error.response) return `${fallback} (HTTP ${error.response.status}).`
  }
  return fallback
}

export default function ShortlistsPage() {
  const { selectedWorkspace } = useAuth()
  const wsId = selectedWorkspace?.workspace_id

  return <WorkspaceShortlists key={wsId ?? 'no-workspace'} wsId={wsId} />
}

function WorkspaceShortlists({ wsId }: { wsId: string | undefined }) {
  const qc = useQueryClient()

  // State declarations must come before queries that use jobId.
  const [jobId, setJobId] = useState('')
  const [candidateId, setCandidateId] = useState('')
  const [confirm, setConfirm] = useState<string | null>(null)
  const [addMessage, setAddMessage] = useState<{ message: string; error: boolean } | null>(null)
  const [removeError, setRemoveError] = useState<string | null>(null)

  // Existing workspace shortlists.
  const { data, isLoading, isError } = useQuery({
    queryKey: ['shortlists', wsId],
    queryFn: async () =>
      (
        await apiClient.get<Shortlist[]>('/shortlists', {
          params: { workspace_id: wsId },
        })
      ).data,
    enabled: !!wsId,
  })

  // Workspace jobs.
  const jobsQ = useQuery({
    queryKey: ['jobs', wsId],
    queryFn: () => fetchJobs(wsId!),
    enabled: !!wsId,
  })

  // Only candidates explicitly assigned to the selected job.
  const candsQ = useQuery({
    queryKey: ['job-candidates', wsId, jobId],
    queryFn: () => fetchJobCandidates(wsId!, jobId),
    enabled: !!wsId && !!jobId,
  })

  const add = useMutation({
    mutationFn: (variables: {
      workspaceId: string
      jobId: string
      candidateId: string
    }) =>
      apiClient.post('/shortlists', {
        workspace_id: variables.workspaceId,
        job_id: variables.jobId,
        candidate_id: variables.candidateId,
      }),

    onSuccess: (response, variables) => {
      setAddMessage({
        message:
          response.status === 200
            ? 'This candidate is already on the selected job shortlist.'
            : 'Candidate added to the selected job shortlist.',
        error: false,
      })

      qc.invalidateQueries({
        queryKey: ['shortlists', variables.workspaceId],
      })

      setCandidateId('')
    },

    onError: error =>
      setAddMessage({
        message: getErrorMessage(error, 'Failed to add candidate.'),
        error: true,
      }),
  })

  const remove = useMutation({
    mutationFn: (variables: {
      workspaceId: string
      shortlistId: string
    }) =>
      apiClient.delete(`/shortlists/${variables.shortlistId}`, {
        params: { workspace_id: variables.workspaceId },
      }),

    onSuccess: (_response, variables) => {
      setConfirm(null)
      setRemoveError(null)

      qc.invalidateQueries({
        queryKey: ['shortlists', variables.workspaceId],
      })
    },

    onError: error =>
      setRemoveError(
        getErrorMessage(error, 'Failed to remove candidate.'),
      ),
  })

  const items = data ?? []

  // Verify that the selected candidate belongs to this job's assignment list.
  const selectedCandidateIsAssigned = (candsQ.data ?? []).some(
    candidate => candidate.candidate_id === candidateId,
  )

  // Prevent duplicate active shortlist entries for the selected job.
  const selectedCandidateAlreadyShortlisted = items.some(
    item =>
      item.job_id === jobId &&
      item.candidate_id === candidateId,
  )

  return (
    <div className="app-shell flex">
      <Sidebar />

      <main className="flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <h1 className="page-title">Shortlisted</h1>
          </div>

          {/* Add candidate to shortlist */}
          <div className="panel max-w-2xl p-4 md:p-5">
            <h2 className="section-title">Add to shortlist</h2>

            <div className="space-y-3">
              <label
                className="block text-sm text-slate-300"
                htmlFor="shortlist-job"
              >
                Job
              </label>

              <StyledSelect
                id="shortlist-job"
                aria-label="Job"
                value={jobId}
                placeholder="Select job"
                options={(jobsQ.data ?? []).map(job => ({
                  value: job.job_id,
                  label: job.title,
                }))}
                disabled={
                  jobsQ.isLoading ||
                  jobsQ.isError ||
                  add.isPending
                }
                onValueChange={value => {
                  setJobId(value)
                  setCandidateId('')
                  setAddMessage(null)
                }}
              />

              <label
                className="block text-sm text-slate-300"
                htmlFor="shortlist-candidate"
              >
                Candidate for{' '}
                {jobsQ.data?.find(job => job.job_id === jobId)?.title ||
                  'selected job'}
              </label>

              <StyledSelect
                id="shortlist-candidate"
                aria-label="Candidate"
                value={candidateId}
                placeholder="Select assigned candidate"
                options={(candsQ.data ?? []).map(candidate => ({
                  value: candidate.candidate_id,
                  label: candidate.full_name,
                }))}
                disabled={
                  !jobId ||
                  candsQ.isLoading ||
                  candsQ.isError ||
                  add.isPending
                }
                onValueChange={value => {
                  setCandidateId(value)
                  setAddMessage(null)
                }}
              />

              {jobsQ.isError && (
                <p role="alert" className="text-sm text-red-300">
                  Failed to load workspace jobs.
                </p>
              )}

              {candsQ.isError && (
                <p role="alert" className="text-sm text-red-300">
                  Failed to load candidates assigned to this job.
                </p>
              )}

              {jobsQ.isLoading && (
                <p role="status" className="text-sm text-slate-300">
                  Loading workspace jobs...
                </p>
              )}

              {jobId && candsQ.isLoading && (
                <p role="status" className="text-sm text-slate-300">
                  Loading candidates assigned to this job...
                </p>
              )}

              {jobId &&
                !candsQ.isLoading &&
                !candsQ.isError &&
                (candsQ.data ?? []).length === 0 && (
                  <p className="text-sm text-slate-400">
                    No candidates are assigned to this job. Assign
                    candidates before adding them to the shortlist.
                  </p>
                )}

              {selectedCandidateAlreadyShortlisted && (
                <p className="text-sm text-amber-200">
                  This candidate is already on the selected job shortlist.
                </p>
              )}

              <button
                onClick={() => {
                  if (
                    wsId &&
                    jobId &&
                    candidateId &&
                    selectedCandidateIsAssigned &&
                    !selectedCandidateAlreadyShortlisted
                  ) {
                    add.mutate({
                      workspaceId: wsId,
                      jobId,
                      candidateId,
                    })
                  }
                }}
                disabled={
                  !wsId ||
                  !jobId ||
                  !candidateId ||
                  !selectedCandidateIsAssigned ||
                  selectedCandidateAlreadyShortlisted ||
                  candsQ.isLoading ||
                  candsQ.isError ||
                  add.isPending
                }
                className="button-primary disabled:cursor-not-allowed disabled:opacity-70"
              >
                {add.isPending ? 'Adding...' : 'Add'}
              </button>

              {addMessage && (
                <p
                  role={addMessage.error ? 'alert' : 'status'}
                  className={`text-sm ${
                    addMessage.error
                      ? 'text-red-300'
                      : 'text-emerald-300'
                  }`}
                >
                  {addMessage.message}
                </p>
              )}
            </div>
          </div>

          {/* Existing shortlist records */}
          {isLoading && (
            <p className="mt-4 text-slate-300">
              Loading shortlists...
            </p>
          )}

          {isError && (
            <p role="alert" className="mt-4 text-red-300">
              Failed to load shortlists.
            </p>
          )}

          {!isLoading && !isError && items.length === 0 && (
            <p className="mt-4 text-slate-300">
              No shortlisted candidates.
            </p>
          )}

          {!isLoading && !isError && items.length > 0 && (
            <div className="panel mt-6 overflow-hidden">
              <table className="table-shell">
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Candidate</th>
                    <th>Title</th>
                    <th></th>
                  </tr>
                </thead>

                <tbody>
                  {items.map(s => (
                    <tr key={s.shortlist_id}>
                      <td className="font-medium text-slate-100">
                        {s.job_title}
                      </td>

                      <td>
                        <Link
                          className="font-medium text-indigo-200 hover:text-white hover:underline"
                          to={`/candidates/${s.candidate_id}`}
                        >
                          {s.candidate_name}
                        </Link>
                      </td>

                      <td className="text-slate-400">
                        {s.current_title ?? '—'}
                      </td>

                      <td>
                        {confirm === s.shortlist_id ? (
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-amber-200">
                              Confirm removal of {s.candidate_name} from{' '}
                              {s.job_title}?
                            </span>

                            <button
                              className="button-ghost text-red-300"
                              disabled={remove.isPending}
                              onClick={() => {
                                if (wsId) {
                                  remove.mutate({
                                    workspaceId: wsId,
                                    shortlistId: s.shortlist_id,
                                  })
                                }
                              }}
                            >
                              {remove.isPending ? 'Removing...' : 'Confirm'}
                            </button>

                            <button
                              className="button-ghost"
                              disabled={remove.isPending}
                              onClick={() => setConfirm(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            className="button-secondary"
                            disabled={remove.isPending}
                            onClick={() => {
                              setRemoveError(null)
                              setConfirm(s.shortlist_id)
                            }}
                          >
                            Remove
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {removeError && (
            <p role="alert" className="mt-3 text-sm text-red-300">
              {removeError}
            </p>
          )}
        </div>
      </main>
    </div>
  )
}