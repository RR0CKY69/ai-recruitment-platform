import { apiClient } from '../../services/apiClient'

export interface MatchResult {
  job_id: string
  candidate_id: string
  candidate_name: string
  current_title?: string | null
  tfidf_similarity: number | null
  skill_coverage: number | null
  experience_compatibility: string | null
  location_compatibility: string | null
  semantic_similarity: number | null
  hybrid_score: number | null
  explanation: { matched_skills?: string[]; missing_skills?: string[]; experience_required?: string; experience_candidate?: string }
}

export const runMatching = (workspaceId: string, jobId: string) =>
  apiClient.post<MatchResult[]>('/matching/run', { workspace_id: workspaceId, job_id: jobId }).then(r => r.data)

export const fetchMatching = (workspaceId: string, jobId?: string) =>
  apiClient.get<MatchResult[]>('/matching', { params: { workspace_id: workspaceId, ...(jobId ? { job_id: jobId } : {}) } }).then(r => r.data)