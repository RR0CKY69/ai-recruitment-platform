import axios from 'axios';
import { tokenStore } from './tokenStore';

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

const REFRESH_URL = '/auth/refresh';
const LOGIN_URL = '/auth/login';
const LOGOUT_URL = '/auth/logout';

let refreshPromise: Promise<string | null> | null = null;

function shouldSkipRefresh(config: any): boolean {
  const url = config?.url ?? '';
  if (typeof url !== 'string') return false;
  if (url.includes(LOGIN_URL)) return true;
  if (url.includes(REFRESH_URL)) return true;
  if (url.includes(LOGOUT_URL)) return true;
  return false;
}

async function performRefresh(): Promise<string | null> {
  try {
    const response = await axios.post(
      apiClient.defaults.baseURL + REFRESH_URL,
      {},
      { withCredentials: true, headers: { 'Content-Type': 'application/json' } },
    );
    const accessToken = response?.data?.access_token ?? null;
    if (accessToken) {
      tokenStore.setToken(accessToken);
      return accessToken;
    }
    tokenStore.clearToken();
    return null;
  } catch (error) {
    tokenStore.clearToken();
    return null;
  }
}

function getRefreshPromise(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

apiClient.interceptors.request.use((config) => {
  const token = tokenStore.getToken();
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as any).Authorization = 'Bearer ' + token;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error?.config;
    if (!originalRequest) {
      return Promise.reject(error);
    }

    const status = error?.response?.status;
    if (status !== 401) {
      return Promise.reject(error);
    }

    if (originalRequest._retry) {
      return Promise.reject(error);
    }

    if (shouldSkipRefresh(originalRequest)) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    const newToken = await getRefreshPromise();
    if (!newToken) {
      window.dispatchEvent(new CustomEvent('auth:expired'));
      return Promise.reject(error);
    }

    originalRequest.headers = originalRequest.headers ?? {};
    (originalRequest.headers as any).Authorization = 'Bearer ' + newToken;
    return apiClient(originalRequest);
  },
);
