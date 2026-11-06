import { apiClient } from '../../services/apiClient'
import type { Candidate } from '../dashboard/api'

export interface CandidateSourceInput {
  provider: string
  source_record_id: string | null
  source_url: string | null
  authorized_basis: string | null
}

export interface CandidateInput {
  full_name: string
  email: string
  current_title: string | null
  summary: string
  experience_years: number | null
  location: string | null
  skills: string[]
  sources: CandidateSourceInput[]
}

export interface CreateCandidateRequest extends CandidateInput {
  workspace_id: string
}

interface ApiCandidate extends Omit<CandidateInput, 'skills' | 'sources'> {
  id: string
  summary: string
  skills: Candidate['skills']
  sources: Candidate['sources']
}

export interface ResumeCandidateDraft {
  full_name?: string
  email?: string
  current_title?: string | null
  summary?: string
  experience_years?: number | null
  location?: string | null
  skills?: string[]
  sources?: CandidateSourceInput[]
}

export interface ResumeUploadResponse {
  parsed_candidate: ResumeCandidateDraft | null
}

export async function createCandidate(input: CreateCandidateRequest): Promise<Candidate> {
  const { data } = await apiClient.post<ApiCandidate>('/candidates', input)
  return mapCandidate(data)
}

export async function updateCandidate(
  workspaceId: string,
  candidateId: string,
  input: CandidateInput,
): Promise<Candidate> {
  const { data } = await apiClient.put<ApiCandidate>(`/candidates/${candidateId}`, {
    ...input,
    workspace_id: workspaceId,
  })
  return mapCandidate(data)
}

export async function uploadCandidateResume(
  workspaceId: string,
  file: File,
): Promise<ResumeUploadResponse> {
  const formData = new FormData()
  formData.append('workspace_id', workspaceId)
  formData.append('file', file)
  const { data } = await apiClient.post<ResumeUploadResponse>('/candidates/resume', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

function mapCandidate(candidate: ApiCandidate): Candidate {
  return {
    candidate_id: candidate.id,
    full_name: candidate.full_name,
    email: candidate.email,
    current_title: candidate.current_title ?? undefined,
    location: candidate.location ?? undefined,
    summary: candidate.summary,
    experience_years: candidate.experience_years,
    skills: candidate.skills,
    sources: candidate.sources,
  }
}
