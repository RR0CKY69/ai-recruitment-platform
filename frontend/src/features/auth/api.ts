import { apiClient } from '../../services/apiClient';
import type { CurrentUser, TokenResponse, Workspace } from '../../types/auth';

let refreshPromise: Promise<TokenResponse> | null = null;

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/login', { email, password });
  return data;
}

export function refresh(): Promise<TokenResponse> {
  if (!refreshPromise) {
    refreshPromise = apiClient
      .post<TokenResponse>('/auth/refresh', {})
      .then(({ data }) => data)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function logout(): Promise<void> {
  try {
    await apiClient.post('/auth/logout', {});
  } catch (e) {
    // Ignore errors; caller will clear local state
  }
}

export async function fetchMe(): Promise<CurrentUser> {
  const { data } = await apiClient.get<CurrentUser>('/auth/me');
  return data;
}

export async function fetchWorkspaces(): Promise<Workspace[]> {
  const { data } = await apiClient.get<Workspace[]>('/workspaces');
  return data;
}
