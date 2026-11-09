import { apiClient } from '../../services/apiClient'

export type WorkspaceRole = 'ADMIN' | 'RECRUITER'

export interface WorkspaceDetail {
  workspace_id: string
  name: string
  slug: string
  role: WorkspaceRole
}

export interface WorkspaceMember {
  membership_id: string
  user_id: string
  full_name: string
  email: string
  role: WorkspaceRole
  created_at: string
}

export interface AddWorkspaceMemberRequest {
  email: string
  role: WorkspaceRole
}

export interface UpdateWorkspaceMemberRoleRequest {
  role: WorkspaceRole
}

export interface UpdateWorkspaceRequest {
  name: string
}

interface RemoveWorkspaceMemberResponse {
  message: string
}

export async function fetchWorkspace(workspaceId: string): Promise<WorkspaceDetail> {
  const { data } = await apiClient.get<WorkspaceDetail>(
    `/workspaces/${workspaceId}`,
  )
  return data
}

export async function fetchWorkspaceMembers(workspaceId: string): Promise<WorkspaceMember[]> {
  const { data } = await apiClient.get<WorkspaceMember[]>(
    `/workspaces/${workspaceId}/members`,
  )
  return data
}

export async function addWorkspaceMember(
  workspaceId: string,
  input: AddWorkspaceMemberRequest,
): Promise<WorkspaceMember> {
  const { data } = await apiClient.post<WorkspaceMember>(
    `/workspaces/${workspaceId}/members`,
    input,
  )
  return data
}

export async function updateWorkspace(
  workspaceId: string,
  input: UpdateWorkspaceRequest,
): Promise<WorkspaceDetail> {
  const { data } = await apiClient.patch<WorkspaceDetail>(
    `/workspaces/${workspaceId}`,
    input,
  )
  return data
}

export async function updateWorkspaceMemberRole(
  workspaceId: string,
  userId: string,
  input: UpdateWorkspaceMemberRoleRequest,
): Promise<WorkspaceMember> {
  const { data } = await apiClient.patch<WorkspaceMember>(
    `/workspaces/${workspaceId}/members/${userId}`,
    input,
  )
  return data
}

export async function removeWorkspaceMember(
  workspaceId: string,
  userId: string,
): Promise<RemoveWorkspaceMemberResponse> {
  const { data } = await apiClient.delete<RemoveWorkspaceMemberResponse>(
    `/workspaces/${workspaceId}/members/${userId}`,
  )
  return data
}
