export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface CurrentUser {
  id: string
  email: string
  full_name: string
  is_active: boolean
}

export interface Workspace {
  workspace_id: string
  name: string
  slug: string
  role: 'ADMIN' | 'RECRUITER'
}