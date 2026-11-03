import { apiClient } from '../../services/apiClient'

export interface Job {
  job_id: string
  title: string
  status: string
  location?: string
  description: string
  required_skills: string[]
  minimum_experience_years: number | null
  employment_type: string | null
  candidate_count: number
}
export interface Candidate {
  candidate_id: string
  full_name: string
  current_title?: string
  location?: string
  summary: string
  experience_years: number | null
  skills: { name: string; normalized_name: string; years_experience: number | null }[]
  sources: { provider: string; source_record_id: string | null; source_url: string | null; authorized_basis: string | null }[]
}
export interface CandidateDetail extends Candidate {
  associated_jobs: {
    job_id: string
    title: string
    status: string
    stage: string
    matching_results: {
      model_name: string
      model_version: string
      tfidf_similarity: number | null
      skill_coverage: number | null
      experience_compatibility: string | null
      location_compatibility: string | null
      hybrid_score: number | null
      updated_at: string
    }[]
  }[]
}
export interface EvaluationNote {
  note_id: string
  author_id: string
  author_name: string | null
  note: string
}
export interface Evaluation {
  evaluation_id?: string | null
  workspace_id?: string
  job_id: string
  legacy_job_id?: string | null
  job_title?: string
  candidate_id: string
  legacy_candidate_id?: string | null
  candidate_name?: string
  current_title?: string | null
  relevance_label: number | null
  review_status: string
  reviewer_id?: string | null
  reviewer_name?: string | null
  notes?: EvaluationNote[]
  updated_at?: string | null
}
export interface ApiHealth { status: string }
export interface MatchScoreBucket { range: string; count: number }
export interface MatchScoreMetricDistribution {
  score_scale: string
  total_scored_matches: number
  buckets: MatchScoreBucket[]
}
export interface MatchScoreDistribution {
  experimental_combined_score: MatchScoreMetricDistribution
  tfidf_similarity: MatchScoreMetricDistribution
}

interface ApiJob {
  id: string
  description: string
  required_skills: string[]
  minimum_experience_years: number | null
  employment_type: string | null
  title: string
  status: string
  location: string | null
  candidate_count: number
}

interface ApiCandidate {
  id: string
  full_name: string
  summary: string
  current_title: string | null
  location: string | null
  experience_years: number | null
  skills: Candidate['skills']
  sources: Candidate['sources']
}

export async function fetchJobs(workspaceId: string): Promise<Job[]> {
  const { data } = await apiClient.get<ApiJob[]>('/jobs', { params: { workspace_id: workspaceId } })
  return data.map(job => ({
    job_id: job.id,
    title: job.title,
    status: job.status,
    location: job.location ?? undefined,
    description: job.description,
    required_skills: job.required_skills,
    minimum_experience_years: job.minimum_experience_years,
    employment_type: job.employment_type,
    candidate_count: job.candidate_count,
  }))
}

export const fetchHealth = () =>
  apiClient.get<ApiHealth>('/health').then(response => response.data)

export async function fetchCandidates(workspaceId: string): Promise<Candidate[]> {
  const { data } = await apiClient.get<ApiCandidate[]>('/candidates', { params: { workspace_id: workspaceId } })
  return data.map(candidate => ({
    candidate_id: candidate.id,
    full_name: candidate.full_name,
    current_title: candidate.current_title ?? undefined,
    location: candidate.location ?? undefined,
    summary: candidate.summary,
    experience_years: candidate.experience_years,
    skills: candidate.skills,
    sources: candidate.sources,
  }))
}

export const fetchCandidate = (workspaceId: string, candidateId: string) =>
  apiClient.get<CandidateDetail>(`/candidates/${candidateId}`, {
    params: { workspace_id: workspaceId },
  }).then(response => response.data)

export const fetchEvaluations = (workspaceId: string) =>
  apiClient.get<Evaluation[]>('/evaluations', { params: { workspace_id: workspaceId } }).then(r => r.data)

export const fetchMatchScoreDistribution = (workspaceId: string) =>
  apiClient.get<MatchScoreDistribution>('/matching/score-distribution', {
    params: { workspace_id: workspaceId },
  }).then(response => response.data)