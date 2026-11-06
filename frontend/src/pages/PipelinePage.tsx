import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRightLeft, LoaderCircle } from 'lucide-react'
import Sidebar from '../components/layout/Sidebar'
import StyledSelect from '../components/shared/StyledSelect'
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  ScoreDisplay,
  SkillChips,
  StatusBadge,
} from '../components/shared/Primitives'
import { useAuth } from '../features/auth/AuthContext'
import { fetchJobs } from '../features/dashboard/api'
import { fetchJobCandidates, updateCandidateStage } from '../features/assignments/api'
import type { JobCandidateAssignment } from '../features/assignments/api'
import { fetchMatching } from '../features/matching/api'
import { getApiErrorMessage } from '../lib/apiErrors'

const STAGE_ORDER = ['SOURCED', 'REVIEWING', 'SHORTLISTED', 'REJECTED', 'HIRED'] as const

type StageKey = (typeof STAGE_ORDER)[number]

export default function PipelinePage() {
  const { selectedWorkspace } = useAuth()
  const workspaceId = selectedWorkspace?.workspace_id
  const [jobId, setJobId] = useState('')

  const jobsQuery = useQuery({
    queryKey: ['jobs', workspaceId],
    queryFn: () => fetchJobs(workspaceId!),
    enabled: !!workspaceId,
  })

  const selectedJob = jobsQuery.data?.find(job => job.job_id === jobId)

  const jobCandidatesQuery = useQuery({
    queryKey: ['job-candidates', workspaceId, jobId],
    queryFn: () => fetchJobCandidates(workspaceId!, jobId),
    enabled: !!workspaceId && !!jobId,
  })

  const qc = useQueryClient()
  const [savingCandidateIds, setSavingCandidateIds] = useState<Set<string>>(new Set())
  const [stageError, setStageError] = useState<{
    candidateId: string
    message: string
  } | null>(null)

  const stageMutation = useMutation({
    mutationFn: async (variables: {
      jobId: string
      candidateId: string
      stage: string
    }) => {
      return updateCandidateStage(workspaceId!, variables.jobId, variables.candidateId, variables.stage)
    },
    onMutate: async variables => {
      await qc.cancelQueries({
        queryKey: ['job-candidates', workspaceId, variables.jobId],
      })

      const previous = qc.getQueryData<JobCandidateAssignment[]>([
        'job-candidates',
        workspaceId,
        variables.jobId,
      ])

      qc.setQueryData<JobCandidateAssignment[]>(
        ['job-candidates', workspaceId, variables.jobId],
        old => {
          if (!old) return old
          return old.map(candidate =>
            candidate.candidate_id === variables.candidateId
              ? { ...candidate, stage: variables.stage }
              : candidate,
          )
        },
      )

      setSavingCandidateIds(prev => new Set(prev).add(variables.candidateId))
      setStageError(null)

      return { previous, jobId: variables.jobId }
    },
    onError: (error, variables, context) => {
      qc.setQueryData(
        ['job-candidates', workspaceId, context?.jobId],
        context?.previous ?? undefined,
      )
      setStageError({
        candidateId: variables.candidateId,
        message: getApiErrorMessage(error, 'Failed to update candidate stage.'),
      })
    },
    onSettled: (_data, _error, variables, context) => {
      setSavingCandidateIds(prev => {
        const next = new Set(prev)
        next.delete(variables.candidateId)
        return next
      })
      qc.invalidateQueries({
        queryKey: [
          'job-candidates',
          workspaceId,
          context?.jobId ?? variables.jobId,
        ],
      })

      qc.invalidateQueries({
        queryKey: ['shortlists', workspaceId],
      })
    },
  })

  const matchingQuery = useQuery({
    queryKey: ['matching', workspaceId, jobId],
    queryFn: () => fetchMatching(workspaceId!, jobId),
    enabled: !!workspaceId && !!jobId,
  })

  const scoreByCandidate = useMemo(() => {
    const next = new Map<string, number | null>()
    for (const result of matchingQuery.data ?? []) {
      next.set(result.candidate_id, result.tfidf_similarity)
    }
    return next
  }, [matchingQuery.data])

  const groupedCandidates = useMemo(() => {
    const buckets: Record<
  StageKey,
  NonNullable<typeof jobCandidatesQuery.data>
> = {
      SOURCED: [],
      REVIEWING: [],
      SHORTLISTED: [],
      REJECTED: [],
      HIRED: [],
    }

    for (const candidate of jobCandidatesQuery.data ?? []) {
      const stage = String(candidate.stage ?? 'SOURCED').toUpperCase() as StageKey
      const bucket = buckets[stage] ? buckets[stage] : buckets.SOURCED
      bucket.push(candidate)
    }

    return buckets
  }, [jobCandidatesQuery.data])

  const hasAnyAssignedCandidates = (jobCandidatesQuery.data ?? []).length > 0

  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <div className="page-shell">
          <PageHeader
            title="Pipeline"
            eyebrow="Recruitment"
            description="Review each assigned candidate by job-specific pipeline stage and move candidates between stages."
            actions={(
              <div className="w-full max-w-xl">
                <StyledSelect
                  aria-label="Job"
                  value={jobId}
                  placeholder="Select job"
                  options={(jobsQuery.data ?? []).map(job => ({ value: job.job_id, label: job.title }))}
                  onValueChange={value => setJobId(value)}
                />
              </div>
            )}
          />

          {jobsQuery.isLoading && <LoadingState label="Loading workspace jobs..." />}
          {jobsQuery.isError && (
            <ErrorState
              title="Failed to load workspace jobs."
              description={getApiErrorMessage(jobsQuery.error, 'Unable to load jobs.')}
            />
          )}

          {!jobsQuery.isLoading && !jobsQuery.isError && !selectedJob && !jobId && (
            <EmptyState title="Choose a job to view the pipeline" description="Assigned candidates appear here grouped by their current stage for the selected job." />
          )}

          {selectedJob && (
            <>
              <section className="panel mb-5 p-4 md:p-5" aria-label="Selected job information">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <h2 className="section-title">{selectedJob.title}</h2>
                    <p className="mt-1 text-sm text-slate-300">{selectedJob.description || 'No job description provided.'}</p>
                  </div>
                  <StatusBadge label={selectedJob.status.replace('_', ' ')} />
                </div>
                <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-300">
                  <span>Experience: {selectedJob.minimum_experience_years == null ? 'Not specified' : `${selectedJob.minimum_experience_years}+ years`}</span>
                  <span>Location: {selectedJob.location || 'Not specified'}</span>
                  <span>Employment: {selectedJob.employment_type || 'Not specified'}</span>
                </div>
                <div className="mt-4">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Required skills</h3>
                  <div className="mt-2">
                    <SkillChips skills={selectedJob.required_skills} label="Required skills" />
                  </div>
                </div>
              </section>

              {jobCandidatesQuery.isLoading && <LoadingState label="Loading assigned candidates..." />}
              {jobCandidatesQuery.isError && (
                <ErrorState
                  title="Failed to load assigned candidates."
                  description={getApiErrorMessage(jobCandidatesQuery.error, 'Unable to load the selected job pipeline.')}
                />
              )}

              {!jobCandidatesQuery.isLoading && !jobCandidatesQuery.isError && !hasAnyAssignedCandidates && (
                <EmptyState
                  title="No assigned candidates yet"
                  description="Candidates must be explicitly assigned to this job before they appear in the pipeline."
                />
              )}

              {!jobCandidatesQuery.isLoading && !jobCandidatesQuery.isError && hasAnyAssignedCandidates && (
                <div className="grid gap-4 xl:grid-cols-5 lg:grid-cols-3 md:grid-cols-2">
                  {STAGE_ORDER.map(stage => {
                    const candidates = groupedCandidates[stage] ?? []

                    return (
                      <section key={stage} className="panel min-h-[260px] p-3">
                        <div className="mb-3 flex items-center justify-between gap-2">
                          <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">{stage}</h2>
                          <StatusBadge label={String(candidates.length)} tone="info" />
                        </div>

                        {candidates.length === 0 ? (
                          <div className="flex min-h-24 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-950/30 p-3 text-center text-sm text-slate-400">
                            No candidates
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {candidates.map(candidate => {
                              const matchScore = scoreByCandidate.get(candidate.candidate_id)
                              const match = matchingQuery.data?.find(item => item.candidate_id === candidate.candidate_id)
                              const matchedSkills = match?.explanation?.matched_skills ?? []
                              const missingSkills = match?.explanation?.missing_skills ?? []

                              return (
                                <article key={candidate.candidate_id} className="rounded-xl border border-slate-700 bg-slate-950/30 p-3">
                                  <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                      <h3 className="truncate font-semibold text-slate-100">{candidate.full_name}</h3>
                                      <p className="mt-1 text-xs text-slate-300">{candidate.current_title || 'Current title unavailable'}</p>
                                    </div>
                                    <ArrowRightLeft size={14} className="mt-1 shrink-0 text-slate-500" aria-hidden="true" />
                                  </div>

                                  <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-300">
                                    <span className="font-medium text-slate-400 uppercase text-[10px] tracking-wider">Stage</span>
                                    <StyledSelect
                                      aria-label={`Stage for ${candidate.full_name}`}
                                      value={candidate.stage}
                                      placeholder="Stage"
                                      options={STAGE_ORDER.map(stage => ({ value: stage, label: stage }))}
                                      disabled={
                                        savingCandidateIds.has(candidate.candidate_id) ||
                                        stageMutation.isPending ||
                                        jobCandidatesQuery.isLoading
                                      }
                                      onValueChange={nextStage => {
                                        if (!workspaceId || !jobId) return
                                        if (
                                          stageMutation.isPending ||
                                          savingCandidateIds.has(candidate.candidate_id)
                                        ) {
                                          return
                                        }
                                        stageMutation.mutate({
                                          jobId,
                                          candidateId: candidate.candidate_id,
                                          stage: nextStage,
                                        })
                                      }}
                                    />
                                    {stageError?.candidateId === candidate.candidate_id && (
                                      <span className="text-xs text-red-300" role="alert">
                                        {stageError.message}
                                      </span>
                                    )}
                                    {savingCandidateIds.has(candidate.candidate_id) && (
                                      <LoaderCircle size={14} className="animate-spin text-slate-400" aria-hidden="true" />
                                    )}
                                  </div>

                                  <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-300">
                                    <span>Experience</span>
                                    <span className="font-medium text-slate-100">{candidate.experience_years == null ? '—' : `${candidate.experience_years} yrs`}</span>
                                  </div>
                                  <div className="mt-1 flex items-center justify-between gap-3 text-xs text-slate-300">
                                    <span>Location</span>
                                    <span className="font-medium text-slate-100 truncate">{candidate.location || 'Unspecified'}</span>
                                  </div>
                                  {matchScore !== undefined && matchScore !== null && (
                                    <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-300">
                                      <span>Match</span>
                                      <ScoreDisplay score={matchScore} max={1} label="TF-IDF" />
                                    </div>
                                  )}

                                  {matchedSkills.length > 0 && (
                                    <div className="mt-3">
                                      <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-400">Matched skills</p>
                                      <SkillChips skills={matchedSkills} label="Matched skills" />
                                    </div>
                                  )}

                                  {missingSkills.length > 0 && (
                                    <div className="mt-3">
                                      <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-400">Missing skills</p>
                                      <SkillChips skills={missingSkills} label="Missing skills" />
                                    </div>
                                  )}
                                </article>
                              )
                            })}
                          </div>
                        )}
                      </section>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  )
}
