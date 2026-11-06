import { apiClient } from '../../services/apiClient'
import type { Job } from '../dashboard/api'

export type JobStatus = 'DRAFT' | 'OPEN' | 'ON_HOLD' | 'CLOSED'

export interface JobInput {
  title: string
  description: string
  required_skills: string[]
  employment_type: string | null
  location: string | null
  minimum_experience_years: number | null
  status: JobStatus
}

export interface CreateJobRequest extends JobInput {
  workspace_id: string
}

interface ApiJob extends JobInput {
  id: string
  candidate_count: number
  location: string | null
}

function mapJob(job: ApiJob): Job {
  return {
    job_id: job.id,
    title: job.title,
    description: job.description,
    required_skills: job.required_skills,
    employment_type: job.employment_type,
    location: job.location ?? undefined,
    minimum_experience_years: job.minimum_experience_years,
    status: job.status,
    candidate_count: job.candidate_count,
  }
}

export async function createJob(input: CreateJobRequest): Promise<Job> {
  const { data } = await apiClient.post<ApiJob>('/jobs', input)
  return mapJob(data)
}

export async function updateJob(
  workspaceId: string,
  jobId: string,
  input: JobInput,
): Promise<Job> {
  const { data } = await apiClient.put<ApiJob>(`/jobs/${jobId}`, {
    ...input,
    workspace_id: workspaceId,
  })
  return mapJob(data)
}
