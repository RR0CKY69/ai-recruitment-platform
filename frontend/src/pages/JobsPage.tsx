import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, PencilLine } from 'lucide-react'
import { useAuth } from '../features/auth/AuthContext'
import { fetchJobs, type Job } from '../features/dashboard/api'
import { createJob, updateJob, type JobInput, type JobStatus } from '../features/jobs/api'
import { getApiErrorMessage } from '../lib/apiErrors'
import Sidebar from '../components/layout/Sidebar'
import SearchField from '../components/shared/SearchField'
import ModalDialog from '../components/shared/ModalDialog'
import StyledSelect from '../components/shared/StyledSelect'
import { EmptyState, StatusBadge } from '../components/shared/Primitives'

const statuses: JobStatus[] = ['DRAFT', 'OPEN', 'ON_HOLD', 'CLOSED']
const statusOptions = [
  { value: 'ALL', label: 'All statuses' },
  ...statuses.map(status => ({ value: status, label: status.replace('_', ' ') })),
]

interface JobDraft {
  title: string
  description: string
  requiredSkills: string
  employmentType: string
  location: string
  experience: string
  status: JobStatus
}

const blankDraft = (): JobDraft => ({
  title: '',
  description: '',
  requiredSkills: '',
  employmentType: '',
  location: '',
  experience: '',
  status: 'OPEN',
})

function draftFromJob(job: Job): JobDraft {
  return {
    title: job.title,
    description: job.description,
    requiredSkills: job.required_skills.join(', '),
    employmentType: job.employment_type ?? '',
    location: job.location ?? '',
    experience: job.minimum_experience_years == null ? '' : String(job.minimum_experience_years),
    status: statuses.includes(job.status as JobStatus) ? job.status as JobStatus : 'OPEN',
  }
}

function inputFromDraft(draft: JobDraft): JobInput {
  return {
    title: draft.title.trim(),
    description: draft.description.trim(),
    required_skills: draft.requiredSkills.split(',').map(skill => skill.trim()).filter(Boolean),
    employment_type: draft.employmentType.trim() || null,
    location: draft.location.trim() || null,
    minimum_experience_years: draft.experience === '' ? null : Number(draft.experience),
    status: draft.status,
  }
}

export default function JobsPage() {
  const { selectedWorkspace } = useAuth()
  const workspaceId = selectedWorkspace?.workspace_id
  const queryClient = useQueryClient()
  const jobsQuery = useQuery({
    queryKey: ['jobs', workspaceId],
    queryFn: () => fetchJobs(workspaceId!),
    enabled: !!workspaceId,
  })
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [editingJob, setEditingJob] = useState<Job | null>(null)
  const [creating, setCreating] = useState(false)

  const createMutation = useMutation({
    mutationFn: (input: JobInput) => createJob({ ...input, workspace_id: workspaceId! }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['jobs', workspaceId] })
      setCreating(false)
    },
  })
  const updateMutation = useMutation({
    mutationFn: (input: JobInput) => updateJob(workspaceId!, editingJob!.job_id, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['jobs', workspaceId] })
      setEditingJob(null)
    },
  })

  const jobs = (jobsQuery.data ?? []).filter(job =>
    job.title.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
    && (statusFilter === 'ALL' || job.status === statusFilter),
  )

  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">Workspace</p>
              <h1 className="page-title">Jobs</h1>
              <p className="mt-2 text-sm text-slate-400">Manage open roles and track their assigned candidates.</p>
            </div>
            <button type="button" className="button-primary inline-flex items-center justify-center gap-2" onClick={() => setCreating(true)}>
              <Plus size={17} aria-hidden="true" /> Create job
            </button>
          </div>

          <div className="mb-5 grid gap-3 sm:grid-cols-[minmax(0,1fr)_12rem]">
            <SearchField label="Search jobs" placeholder="Search by job title" value={query} onChange={setQuery} />
            <StyledSelect
              aria-label="Filter jobs by status"
              value={statusFilter}
              options={statusOptions}
              onValueChange={setStatusFilter}
            />
          </div>

          {!workspaceId && <p className="text-sm text-slate-300">Select a workspace to view its jobs.</p>}
          {jobsQuery.isLoading && <p role="status" className="text-sm text-slate-300">Loading workspace jobs...</p>}
          {jobsQuery.isError && <p role="alert" className="text-sm text-red-300">{getApiErrorMessage(jobsQuery.error, 'Failed to load workspace jobs.')}</p>}
          {workspaceId && !jobsQuery.isLoading && !jobsQuery.isError && jobs.length === 0 && (
            <EmptyState
              title={(query || statusFilter !== 'ALL') ? 'No matching jobs' : 'No jobs in this workspace'}
              description={(query || statusFilter !== 'ALL') ? 'Try adjusting the title search or status filter.' : 'Create a job to start organizing your hiring pipeline.'}
            />
          )}
          {workspaceId && !jobsQuery.isLoading && !jobsQuery.isError && jobs.length > 0 && (
            <div className="panel hidden overflow-hidden md:block">
              <div className="table-scroll">
                <table className="table-shell">
                  <thead>
                    <tr>
                      <th>Job title</th>
                      <th>Location</th>
                      <th>Employment type</th>
                      <th>Status</th>
                      <th>Assigned candidates</th>
                      <th><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map(job => (
                      <tr key={job.job_id}>
                        <td className="font-medium text-slate-100">
                          <Link className="text-indigo-200 underline-offset-4 hover:text-white hover:underline" to={`/jobs/${job.job_id}`}>
                            {job.title}
                          </Link>
                        </td>
                        <td className="text-slate-300">{job.location ?? '—'}</td>
                        <td className="text-slate-300">{job.employment_type ?? '—'}</td>
                        <td><StatusBadge label={job.status.replace('_', ' ')} /></td>
                        <td className="text-slate-300">{job.candidate_count}</td>
                        <td>
                          <button
                            type="button"
                            className="button-ghost inline-flex items-center gap-2 px-3 py-2 text-xs"
                            aria-label={`Edit ${job.title}`}
                            onClick={() => setEditingJob(job)}
                          >
                            <PencilLine size={14} aria-hidden="true" /> Edit
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {workspaceId && !jobsQuery.isLoading && !jobsQuery.isError && jobs.length > 0 && (
            <ul className="grid gap-3 md:hidden">
              {jobs.map(job => (
                <li key={job.job_id} className="panel min-w-0 p-4">
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <Link className="break-words font-semibold text-indigo-100 hover:text-white hover:underline" to={`/jobs/${job.job_id}`}>
                      {job.title}
                    </Link>
                    <StatusBadge label={job.status.replace('_', ' ')} />
                  </div>
                  <div className="mt-3 grid gap-2 text-sm text-slate-400">
                    <p>{job.location ?? 'Location unavailable'}</p>
                    <p>{job.employment_type ?? 'Employment type unavailable'}</p>
                    <p>{job.candidate_count} assigned candidates</p>
                  </div>
                  <button
                    type="button"
                    className="button-ghost mt-3 inline-flex items-center gap-2 px-3 py-2 text-xs"
                    aria-label={`Edit ${job.title}`}
                    onClick={() => setEditingJob(job)}
                  >
                    <PencilLine size={14} aria-hidden="true" /> Edit
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>

      <JobEditorDialog
        open={creating || !!editingJob}
        job={editingJob}
        pending={createMutation.isPending || updateMutation.isPending}
        error={createMutation.error || updateMutation.error}
        onClose={() => {
          if (createMutation.isPending || updateMutation.isPending) return
          setCreating(false)
          setEditingJob(null)
          createMutation.reset()
          updateMutation.reset()
        }}
        onSubmit={input => editingJob ? updateMutation.mutate(input) : createMutation.mutate(input)}
      />
    </div>
  )
}

export function JobEditorDialog({
  open,
  job,
  pending,
  error,
  onClose,
  onSubmit,
}: {
  open: boolean
  job: Job | null
  pending: boolean
  error: unknown
  onClose: () => void
  onSubmit: (input: JobInput) => void
}) {
  const [draft, setDraft] = useState<JobDraft>(blankDraft)
  useEffect(() => {
    if (open) setDraft(job ? draftFromJob(job) : blankDraft())
  }, [open, job?.job_id])

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (draft.experience !== '' && (!Number.isInteger(Number(draft.experience)) || Number(draft.experience) < 0)) return
    onSubmit(inputFromDraft(draft))
  }
  const setField = <K extends keyof JobDraft>(key: K, value: JobDraft[K]) =>
    setDraft(current => ({ ...current, [key]: value }))

  return (
    <ModalDialog open={open} title={job ? 'Edit job' : 'Create job'} onClose={onClose}>
      <form className="space-y-4" onSubmit={submit}>
        <label className="form-field">
          <span>Job title *</span>
          <input required maxLength={200} className="input-shell" value={draft.title} onChange={event => setField('title', event.target.value)} />
        </label>
        <label className="form-field">
          <span>Job description *</span>
          <textarea required rows={4} className="textarea-shell" value={draft.description} onChange={event => setField('description', event.target.value)} />
        </label>
        <label className="form-field">
          <span>Required skills</span>
          <input className="input-shell" value={draft.requiredSkills} onChange={event => setField('requiredSkills', event.target.value)} placeholder="Python, SQL, ..." />
          <span className="text-xs text-slate-400">Separate skills with commas.</span>
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="form-field">
            <span>Employment type</span>
            <input maxLength={100} className="input-shell" value={draft.employmentType} onChange={event => setField('employmentType', event.target.value)} />
          </label>
          <label className="form-field">
            <span>Location</span>
            <input maxLength={200} className="input-shell" value={draft.location} onChange={event => setField('location', event.target.value)} />
          </label>
          <label className="form-field">
            <span>Minimum experience (years)</span>
            <input type="number" min="0" step="1" className="input-shell" value={draft.experience} onChange={event => setField('experience', event.target.value)} />
          </label>
          <label className="form-field">
            <span>Status</span>
            <StyledSelect
              aria-label="Job status"
              value={draft.status}
              options={statuses.map(status => ({ value: status, label: status.replace('_', ' ') }))}
              onValueChange={value => setField('status', value as JobStatus)}
            />
          </label>
        </div>
        {!!error && <p role="alert" className="text-sm text-red-300">{getApiErrorMessage(error, 'Unable to save this job.')}</p>}
        <div className="flex flex-wrap justify-end gap-3 pt-1">
          <button type="button" className="button-ghost" disabled={pending} onClick={onClose}>Cancel</button>
          <button type="submit" className="button-primary" disabled={pending}>
            {pending ? 'Saving...' : job ? 'Save changes' : 'Create job'}
          </button>
        </div>
      </form>
    </ModalDialog>
  )
}
