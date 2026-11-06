export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface RegistrationRequest {
  full_name: string
  email: string
  password: string
  workspace_name: string
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