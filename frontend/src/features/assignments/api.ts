import { apiClient } from '../../services/apiClient'
import type { Candidate } from '../dashboard/api'

export interface JobCandidateAssignment extends Candidate {
  stage: string
}

export interface AssignCandidateRequest {
  workspace_id: string
  candidate_id: string
}

export interface UpdateCandidateStageRequest {
  stage: string
}

export interface UpdateCandidateStageResponse {
  candidate_id: string
  stage: string
}

interface ApiJobCandidateAssignment {
  candidate_id: string
  full_name: string
  email?: string | null
  current_title: string | null
  summary: string
  experience_years: number | null
  location: string | null
  skills: Candidate['skills']
  sources: Candidate['sources']
  stage: string
}

export async function fetchJobCandidates(
  workspaceId: string,
  jobId: string,
): Promise<JobCandidateAssignment[]> {
  const { data } = await apiClient.get<ApiJobCandidateAssignment[]>(`/jobs/${jobId}/candidates`, {
    params: { workspace_id: workspaceId },
  })
  return data.map(mapAssignment)
}

export async function assignCandidateToJob(
  jobId: string,
  input: AssignCandidateRequest,
): Promise<JobCandidateAssignment> {
  const { data } = await apiClient.post<ApiJobCandidateAssignment>(
    `/jobs/${jobId}/candidates`,
    input,
  )
  return mapAssignment(data)
}

export async function removeCandidateFromJob(
  workspaceId: string,
  jobId: string,
  candidateId: string,
): Promise<void> {
  await apiClient.delete(`/jobs/${jobId}/candidates/${candidateId}`, {
    params: { workspace_id: workspaceId },
  })
}

export async function updateCandidateStage(
  workspaceId: string,
  jobId: string,
  candidateId: string,
  stage: string,
): Promise<JobCandidateAssignment> {
  const { data } = await apiClient.patch<ApiJobCandidateAssignment>(
    `/jobs/${jobId}/candidates/${candidateId}`,
    { stage },
    { params: { workspace_id: workspaceId } },
  )
  return mapAssignment(data)
}

function mapAssignment(assignment: ApiJobCandidateAssignment): JobCandidateAssignment {
  return {
    candidate_id: assignment.candidate_id,
    full_name: assignment.full_name,
    email: assignment.email ?? undefined,
    current_title: assignment.current_title ?? undefined,
    summary: assignment.summary,
    experience_years: assignment.experience_years,
    location: assignment.location ?? undefined,
    skills: assignment.skills,
    sources: assignment.sources,
    stage: assignment.stage,
  }
}
