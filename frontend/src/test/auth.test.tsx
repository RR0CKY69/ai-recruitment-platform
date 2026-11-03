import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AxiosError } from 'axios';
import { AuthProvider, useAuth } from '../features/auth/AuthContext';
import { tokenStore } from '../services/tokenStore';

vi.mock('../features/auth/api', async () => {
  const actual = await vi.importActual<any>('../features/auth/api');
  return {
    ...actual,
    refresh: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    fetchMe: vi.fn(),
    fetchWorkspaces: vi.fn(),
  };
});

import * as authApi from '../features/auth/api';

describe('Auth migration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    tokenStore.clearToken();
  });

  it('successful startup refresh sets token in memory and loads user/workspaces', async () => {
    (authApi.refresh as any).mockResolvedValue({ access_token: 'at1', token_type: 'bearer', expires_in: 900 });
    (authApi.fetchMe as any).mockResolvedValue({ id: 'u1', email: 'a@b.com', full_name: 'A', is_active: true });
    (authApi.fetchWorkspaces as any).mockResolvedValue([{ workspace_id: 'w1', name: 'W', slug: 'w', role: 'ADMIN' }]);

    const TestComp = () => {
      const { token, user } = useAuth();
      return <div>{token ? 'ok' : 'no'}:{user?.email ?? 'none'}</div>;
    };

    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <TestComp />
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/ok:a@b.com/)).toBeTruthy();
    });
    expect(tokenStore.getToken()).toBe('at1');
  });

  it('failed startup refresh remains unauthenticated', async () => {
    (authApi.refresh as any).mockRejectedValue(new Error('fail'));

    const TestComp = () => {
      const { token } = useAuth();
      return <div>{token ? 'ok' : 'no'}</div>;
    };

    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <TestComp />
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('no')).toBeTruthy();
    });
    expect(tokenStore.getToken()).toBe(null);
  });

  it('login does not use persistent storage', async () => {
    (authApi.refresh as any).mockRejectedValue(new Error('no'));
    (authApi.login as any).mockResolvedValue({ access_token: 'at2', token_type: 'bearer', expires_in: 900 });
    (authApi.fetchMe as any).mockResolvedValue({ id: 'u1', email: 'a@b.com', full_name: 'A', is_active: true });
    (authApi.fetchWorkspaces as any).mockResolvedValue([]);

    const TestComp = () => {
      const { signIn, token } = useAuth();
      return (
        <div>
          <button onClick={() => signIn('a@b.com', 'p')}>login</button>
          <div>{token ? 'ok' : 'no'}</div>
        </div>
      );
    };

    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <TestComp />
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(authApi.refresh).toHaveBeenCalled());
    screen.getByText('login').click();

    await waitFor(() => {
      expect(screen.getByText('ok')).toBeTruthy();
    });
    expect(sessionStorage.getItem('auth_token')).toBe(null);
    expect(localStorage.getItem('auth_token')).toBe(null);
    expect(tokenStore.getToken()).toBe('at2');
  });

  it('reports the API URL when login cannot connect to the backend', async () => {
    (authApi.refresh as any).mockRejectedValue(new Error('no'));
    (authApi.login as any).mockRejectedValue(new AxiosError('Network Error', 'ERR_NETWORK'));

    const TestComp = () => {
      const { signIn, error } = useAuth();
      return (
        <div>
          <button onClick={() => signIn('a@b.com', 'p').catch(() => undefined)}>login</button>
          <div>{error}</div>
        </div>
      );
    };

    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <TestComp />
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(authApi.refresh).toHaveBeenCalled());
    screen.getByText('login').click();

    await waitFor(() => {
      expect(screen.getByText(/Unable to connect to the API at http:\/\/localhost:8000/)).toBeTruthy();
    });
  });

  it('logout calls backend and clears memory state even on failure', async () => {
    (authApi.refresh as any).mockResolvedValue({ access_token: 'at3', token_type: 'bearer', expires_in: 900 });
    (authApi.fetchMe as any).mockResolvedValue({ id: 'u1', email: 'a@b.com', full_name: 'A', is_active: true });
    (authApi.fetchWorkspaces as any).mockResolvedValue([]);
    (authApi.logout as any).mockRejectedValue(new Error('fail'));

    const TestComp = () => {
      const { signOut, token } = useAuth();
      return (
        <div>
          <button onClick={() => signOut()}>out</button>
          <div>{token ? 'ok' : 'no'}</div>
        </div>
      );
    };

    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <TestComp />
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText('ok')).toBeTruthy());
    screen.getByText('out').click();

    await waitFor(() => {
      expect(screen.getByText('no')).toBeTruthy();
    });
    expect(authApi.logout).toHaveBeenCalled();
    expect(tokenStore.getToken()).toBe(null);
  });
});
