import { useState } from 'react'
import axios from 'axios'
import { useAuth } from '../features/auth/AuthContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { Evaluation } from '../features/dashboard/api'
import { fetchJobs } from '../features/dashboard/api'
import { fetchJobCandidates } from '../features/assignments/api'
import { apiClient } from '../services/apiClient'
import Sidebar from '../components/layout/Sidebar'
import StyledSelect from '../components/shared/StyledSelect'
import ModalDialog from '../components/shared/ModalDialog'
import {
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
} from '../components/shared/Primitives'

export default function EvaluationsPage() {
  const { selectedWorkspace, user } = useAuth()
  const wsId = selectedWorkspace?.workspace_id
  const qc = useQueryClient()

  const [jobId, setJobId] = useState('')
  const [editing, setEditing] = useState<Evaluation | null>(null)
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null)
  const [label, setLabel] = useState<number>(1)
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState<string | null>(null)

  const jobsQuery = useQuery({
    queryKey: ['jobs', wsId],
    queryFn: () => fetchJobs(wsId!),
    enabled: !!wsId,
  })

  const jobs = jobsQuery.data ?? []
  const selectedJobId = jobId || jobs[0]?.job_id || ''

  const assignmentsQuery = useQuery({
    queryKey: ['job-candidates', wsId, selectedJobId],
    queryFn: () => fetchJobCandidates(wsId!, selectedJobId),
    enabled: !!wsId && !!selectedJobId,
  })

  const evaluationsQuery = useQuery({
    queryKey: ['evaluations', wsId],
    queryFn: async () =>
      (
        await apiClient.get<Evaluation[]>('/evaluations', {
          params: { workspace_id: wsId },
        })
      ).data,
    enabled: !!wsId,
  })

  const upsert = useMutation({
    mutationFn: async () => {
      if (!editing) throw new Error('No evaluation selected.')

      const feedback = note.trim()

      return apiClient.put('/evaluations', {
        workspace_id: wsId,
        job_id: editing.job_id,
        candidate_id: editing.candidate_id,
        relevance_label: label,
        review_status: 'reviewed',
        note: feedback || null,
        note_id: feedback ? editingNoteId : null,
        expected_updated_at: editing.updated_at,
      })
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['evaluations', wsId] })
      setMsg('Saved')
      setEditing(null)
      setEditingNoteId(null)
    },
    onError: error => {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        setMsg('This evaluation changed since it was loaded. Refresh and try again.')
      } else if (axios.isAxiosError(error) && error.response?.status === 403) {
        setMsg('You are not authorized to edit this evaluation.')
      } else {
        setMsg('Unable to save evaluation. Please try again.')
      }
    },
  })

  const assignedCandidateIds = new Set(
    (assignmentsQuery.data ?? []).map(candidate => candidate.candidate_id),
  )

  const items = (evaluationsQuery.data ?? []).filter(
    evaluation =>
      evaluation.job_id === selectedJobId &&
      assignedCandidateIds.has(evaluation.candidate_id),
  )

  const isLoading =
    jobsQuery.isLoading ||
    evaluationsQuery.isLoading ||
    (!!selectedJobId && assignmentsQuery.isLoading)

  const isError =
    jobsQuery.isError ||
    evaluationsQuery.isError ||
    (!!selectedJobId && assignmentsQuery.isError)

  return (
    <div className="app-shell flex">
      <Sidebar />

      <main className="flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <h1 className="page-title">Evaluations</h1>
          </div>

          {msg && (
            <p className={`mb-4 text-sm ${msg === 'Saved' ? 'text-emerald-300' : 'text-red-300'}`}>
              {msg}
            </p>
          )}

          {jobsQuery.isSuccess && jobs.length > 0 && (
            <div className="mb-6 max-w-md">
              <label className="mb-2 block text-sm font-medium text-slate-300">
                Select job
              </label>
              <StyledSelect
                aria-label="Select job"
                value={selectedJobId}
                options={jobs.map(job => ({
                  value: job.job_id,
                  label: job.title,
                }))}
                onValueChange={value => {
                  setJobId(value)
                  setEditing(null)
                  setMsg(null)
                }}
              />
            </div>
          )}

          {isLoading && <LoadingState label="Loading evaluations..." />}

          {isError && <ErrorState title="Failed to load evaluations." />}

          {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length === 0 && (
            <EmptyState
              title="No jobs available"
              description="Create a job before reviewing evaluations."
            />
          )}

          {!isLoading && !isError && jobs.length > 0 && assignmentsQuery.isSuccess && (
            <>
              {assignmentsQuery.data.length === 0 ? (
                <EmptyState
                  title="No candidates assigned"
                  description="Assign candidates to this job before reviewing their evaluations."
                />
              ) : items.length === 0 ? (
                <EmptyState
                  title="No evaluation pairs"
                  description="Evaluation items for candidates assigned to this job will appear here when they are ready for review."
                />
              ) : (
                <div className="panel overflow-hidden">
                  <table className="table-shell">
                    <thead>
                      <tr>
                        <th>Job</th>
                        <th>Candidate</th>
                        <th>Status</th>
                        <th>Label</th>
                        <th>Feedback</th>
                        <th></th>
                      </tr>
                    </thead>

                    <tbody>
                      {items.map(e => (
                        <tr
                          key={`${e.job_id}-${e.candidate_id}-${e.evaluation_id ?? 'pending'}`}
                        >
                          <td className="font-medium text-slate-100">
                            {e.job_title}
                          </td>

                          <td className="text-slate-100">{e.candidate_name}</td>

                          <td>
                            <StatusBadge label={e.review_status} />
                          </td>

                          <td>{e.relevance_label ?? '-'}</td>

                          <td>
                            {e.notes?.map(existingNote => existingNote.note).join(' · ') || '-'}
                          </td>

                          <td>
                            {!e.reviewer_id || e.reviewer_id === user?.id ? (
                              <button
                                type="button"
                                className="button-secondary"
                                onClick={() => {
                                  const ownNote = e.notes?.find(
                                    existingNote => existingNote.author_id === user?.id,
                                  )

                                  setEditing(e)
                                  setEditingNoteId(ownNote?.note_id ?? null)
                                  setLabel(e.relevance_label ?? 1)
                                  setNote(ownNote?.note ?? '')
                                  setMsg(null)
                                }}
                              >
                                Edit
                              </button>
                            ) : (
                              <span className="text-slate-400">Read-only</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          <ModalDialog
            open={Boolean(editing)}
            title="Edit evaluation"
            onClose={() => setEditing(null)}
          >
            <div className="space-y-3">
              <StyledSelect
                aria-label="Relevance label"
                value={String(label)}
                options={[
                  { value: '0', label: '0 - Not relevant' },
                  { value: '1', label: '1 - Partial' },
                  { value: '2', label: '2 - Relevant' },
                ]}
                onValueChange={value => setLabel(Number(value))}
              />

              <textarea
                aria-label="Feedback"
                className="textarea-shell min-h-24"
                value={note}
                onChange={e => setNote(e.target.value)}
                placeholder="Note"
              />

              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setEditing(null)}
                  className="button-secondary"
                >
                  Cancel
                </button>

                <button
                  type="button"
                  disabled={upsert.isPending}
                  onClick={() => upsert.mutate()}
                  className="button-primary disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {upsert.isPending ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          </ModalDialog>
        </div>
      </main>
    </div>
  )
}