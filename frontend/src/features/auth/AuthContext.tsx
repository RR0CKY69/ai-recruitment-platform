import axios from 'axios';
import { createContext, useContext, useEffect, useState } from 'react';
import { apiClient } from '../../services/apiClient';
import { tokenStore } from '../../services/tokenStore';
import { fetchMe, fetchWorkspaces, login as loginApi, logout as logoutApi, refresh as refreshApi } from './api';
import type { CurrentUser, Workspace } from '../../types/auth';

interface AuthContextValue {
  token: string | null;
  user: CurrentUser | null;
  workspaces: Workspace[];
  selectedWorkspace: Workspace | null;
  loading: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  selectWorkspace: (w: Workspace) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => tokenStore.getToken());
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspace, setSelectedWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = apiClient.interceptors.request.use((config) => {
      const t = tokenStore.getToken();
      if (t) {
        config.headers = config.headers ?? {};
        (config.headers as any).Authorization = 'Bearer ' + t;
      }
      return config;
    });
    return () => apiClient.interceptors.request.eject(id);
  }, []);

  useEffect(() => {
    const handler = () => {
      tokenStore.clearToken();
      setToken(null);
      setUser(null);
      setWorkspaces([]);
      setSelectedWorkspace(null);
    };
    window.addEventListener('auth:expired', handler);
    return () => window.removeEventListener('auth:expired', handler);
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await refreshApi();
        const accessToken = res?.access_token ?? null;
        if (accessToken) {
          tokenStore.setToken(accessToken);
          if (!active) return;
          setToken(accessToken);
          try {
            const u = await fetchMe();
            const ws = await fetchWorkspaces();
            if (!active) return;
            setUser(u);
            setWorkspaces(ws);
            setSelectedWorkspace(ws[0] ?? null);
          } catch {
            tokenStore.clearToken();
            if (!active) return;
            setToken(null);
            setUser(null);
            setWorkspaces([]);
            setSelectedWorkspace(null);
          }
        } else {
          tokenStore.clearToken();
          if (!active) return;
          setToken(null);
          setUser(null);
          setWorkspaces([]);
          setSelectedWorkspace(null);
        }
      } catch {
        tokenStore.clearToken();
        if (!active) return;
        setToken(null);
        setUser(null);
        setWorkspaces([]);
        setSelectedWorkspace(null);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const signIn = async (email: string, password: string) => {
    setError(null);
    setLoading(true);
    try {
      const res = await loginApi(email, password);
      const accessToken = res?.access_token ?? null;
      if (accessToken) {
        tokenStore.setToken(accessToken);
        setToken(accessToken);
        try {
          const u = await fetchMe();
          const ws = await fetchWorkspaces();
          setUser(u);
          setWorkspaces(ws);
          setSelectedWorkspace(ws[0] ?? null);
        } catch {
          setUser(null);
          setWorkspaces([]);
        }
      } else {
        tokenStore.clearToken();
        setToken(null);
      }
    } catch (e: unknown) {
      tokenStore.clearToken();
      setToken(null);
      setUser(null);
      setWorkspaces([]);
      setSelectedWorkspace(null);
      const response = axios.isAxiosError(e) ? e.response : undefined;
      const detail = response?.data?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : response
            ? `Login failed (HTTP ${response.status}).`
            : `Unable to connect to the API at ${apiClient.defaults.baseURL}. Check that the backend is running.`,
      );
      throw e;
    } finally {
      setLoading(false);
    }
  };

  const signOut = async () => {
    try {
      await logoutApi();
    } catch {
      // ignore
    } finally {
      tokenStore.clearToken();
      setToken(null);
      setUser(null);
      setWorkspaces([]);
      setSelectedWorkspace(null);
      setError(null);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        workspaces,
        selectedWorkspace,
        loading,
        error,
        signIn,
        signOut,
        selectWorkspace: setSelectedWorkspace,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
