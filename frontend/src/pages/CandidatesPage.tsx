import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useAuth } from '../features/auth/AuthContext'
import { fetchCandidates } from '../features/dashboard/api'
import { createCandidate, type CandidateInput } from '../features/candidates/api'
import CandidateEditorDialog from '../components/candidates/CandidateEditorDialog'
import ResumeUploadDialog from '../components/candidates/ResumeUploadDialog'
import type { ResumeCandidateDraft } from '../features/candidates/api'
import Sidebar from '../components/layout/Sidebar'
import SearchField from '../components/shared/SearchField'
import StyledSelect from '../components/shared/StyledSelect'
import { EmptyState, SkillChips } from '../components/shared/Primitives'
import { getApiErrorMessage } from '../lib/apiErrors'

export default function CandidatesPage() {
  const { selectedWorkspace } = useAuth()
  const workspaceId = selectedWorkspace?.workspace_id
  const queryClient = useQueryClient()
  const candidatesQuery = useQuery({
    queryKey: ['candidates', workspaceId],
    queryFn: () => fetchCandidates(workspaceId!),
    enabled: !!workspaceId,
  })
  const [query, setQuery] = useState('')
  const [skillFilter, setSkillFilter] = useState('ALL')
  const [experienceFilter, setExperienceFilter] = useState('ALL')
  const [creating, setCreating] = useState(false)
  const [uploadingResume, setUploadingResume] = useState(false)
  const [resumeDraft, setResumeDraft] = useState<ResumeCandidateDraft | null>(null)
  const createMutation = useMutation({
    mutationFn: (input: CandidateInput) =>
      createCandidate({ ...input, workspace_id: workspaceId! }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['candidates', workspaceId] })
      setCreating(false)
      setResumeDraft(null)
    },
  })

  const candidates = candidatesQuery.data ?? []
  const skills = [...new Set(candidates.flatMap(candidate => candidate.skills.map(skill => skill.name)))]
    .sort((left, right) => left.localeCompare(right))
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const visibleCandidates = candidates.filter(candidate => {
    const searchable = [
      candidate.full_name,
      candidate.email ?? '',
      candidate.current_title ?? '',
      candidate.location ?? '',
      ...candidate.skills.map(skill => skill.name),
    ].join(' ').toLocaleLowerCase()
    return searchable.includes(normalizedQuery)
      && (skillFilter === 'ALL' || candidate.skills.some(skill => skill.name === skillFilter))
      && (experienceFilter === 'ALL'
        || (experienceFilter === 'UNKNOWN' && candidate.experience_years == null)
        || (experienceFilter === '0-2' && candidate.experience_years != null && candidate.experience_years <= 2)
        || (experienceFilter === '3-5' && candidate.experience_years != null && candidate.experience_years >= 3 && candidate.experience_years <= 5)
        || (experienceFilter === '6+' && candidate.experience_years != null && candidate.experience_years >= 6))
  })

  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">Workspace talent</p>
              <h1 className="page-title">Candidates</h1>
              <p className="mt-2 text-sm text-slate-400">Workspace profiles can be reused across multiple jobs.</p>
            </div>
            <div className="flex w-full flex-wrap gap-2 sm:w-auto">
              <button type="button" className="button-secondary" onClick={() => setUploadingResume(true)}>Upload resume</button>
              <button type="button" className="button-primary inline-flex items-center justify-center gap-2" onClick={() => { setResumeDraft(null); setCreating(true) }}>
                <Plus size={17} aria-hidden="true" /> Add candidate
              </button>
            </div>
          </div>

          <div className="mb-5 grid gap-3 sm:grid-cols-[minmax(0,1fr)_12rem_12rem]">
            <SearchField label="Search candidates" placeholder="Search name, email, title, location or skills" value={query} onChange={setQuery} />
            <StyledSelect
              aria-label="Filter candidates by skill"
              value={skillFilter}
              options={[
                { value: 'ALL', label: 'All skills' },
                ...skills.map(skill => ({ value: skill, label: skill })),
              ]}
              onValueChange={setSkillFilter}
            />
            <StyledSelect
              aria-label="Filter candidates by experience"
              value={experienceFilter}
              options={[
                { value: 'ALL', label: 'Any experience' },
                { value: '0-2', label: '0–2 years' },
                { value: '3-5', label: '3–5 years' },
                { value: '6+', label: '6+ years' },
                { value: 'UNKNOWN', label: 'Not specified' },
              ]}
              onValueChange={setExperienceFilter}
            />
          </div>

          {!workspaceId && <p className="text-sm text-slate-300">Select a workspace to view candidates.</p>}
          {candidatesQuery.isLoading && <p role="status" className="text-sm text-slate-300">Loading workspace candidates...</p>}
          {candidatesQuery.isError && <p role="alert" className="text-sm text-red-300">{getApiErrorMessage(candidatesQuery.error, 'Failed to load workspace candidates.')}</p>}
          {workspaceId && !candidatesQuery.isLoading && !candidatesQuery.isError && visibleCandidates.length === 0 && (
            <EmptyState
              title={(query || skillFilter !== 'ALL' || experienceFilter !== 'ALL') ? 'No matching candidates' : 'No candidates in this workspace'}
              description={(query || skillFilter !== 'ALL' || experienceFilter !== 'ALL') ? 'Try another search or profile filter.' : 'Add a candidate profile to build your workspace talent pool.'}
            />
          )}
          {workspaceId && !candidatesQuery.isLoading && !candidatesQuery.isError && visibleCandidates.length > 0 && (
            <ul className="grid min-w-0 gap-4 lg:grid-cols-2">
              {visibleCandidates.map(candidate => (
                <li key={candidate.candidate_id} className="panel min-w-0 p-4 transition hover:border-indigo-400/40 md:p-5">
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Link className="break-words text-lg font-semibold text-indigo-100 hover:text-white hover:underline" to={`/candidates/${candidate.candidate_id}`}>
                        {candidate.full_name}
                      </Link>
                      <p className="mt-1 break-words text-sm text-slate-300">{candidate.current_title ?? 'Title unavailable'}</p>
                    </div>
                    <span className="shrink-0 rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-300">
                      {candidate.experience_years == null ? 'Experience unavailable' : `${candidate.experience_years} yrs`}
                    </span>
                  </div>
                  <div className="mt-4 grid gap-2 text-sm text-slate-400 sm:grid-cols-2">
                    <p className="break-all">{candidate.email ?? 'Email unavailable from current API'}</p>
                    <p className="break-words">{candidate.location ?? 'Location unavailable'}</p>
                    <p className="sm:col-span-2">Source: {candidate.sources.map(source => source.provider).join(', ') || 'Unavailable'}</p>
                  </div>
                  <div className="mt-4">
                    <SkillChips skills={candidate.skills.map(skill => skill.name)} />
                  </div>
                  <p className="mt-4 line-clamp-3 text-sm leading-6 text-slate-400">{candidate.summary || 'No professional summary.'}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
      <CandidateEditorDialog
        open={creating}
        initialDraft={resumeDraft}
        title={resumeDraft ? 'Review candidate information' : 'Create candidate profile'}
        pending={createMutation.isPending}
        error={createMutation.error}
        onClose={() => {
          if (createMutation.isPending) return
          setCreating(false)
          setResumeDraft(null)
          createMutation.reset()
        }}
        onSubmit={input => createMutation.mutate(input)}
      />
      {workspaceId && (
        <ResumeUploadDialog
          open={uploadingResume}
          workspaceId={workspaceId}
          onClose={() => setUploadingResume(false)}
          onReview={draft => {
            setResumeDraft(draft)
            setCreating(true)
          }}
        />
      )}
    </div>
  )
}
