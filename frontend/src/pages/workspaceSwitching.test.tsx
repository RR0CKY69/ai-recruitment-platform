import React, { useState, createContext } from 'react'
import { vi, beforeEach } from 'vitest'

const WsContext = createContext('ws-1')
;(globalThis as any).__WsContext = WsContext

vi.mock('../services/apiClient', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() },
}))
vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => {
    const id = React.useContext((globalThis as any).__WsContext)
    return { selectedWorkspace: { workspace_id: id }, loading: false }
  },
}))

import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { apiClient } from '../services/apiClient'
import ShortlistsPage from './ShortlistsPage'

function Wrapper({ children }: { children: React.ReactNode }) {
  const [ws, setWs] = useState('ws-1')
  ;(globalThis as any).__setWs = setWs
  return <WsContext.Provider value={ws}>{children}</WsContext.Provider>
}

beforeEach(() => {
  (apiClient.get as any).mockReset()
  ;(globalThis as any).__wsSet = undefined
})

test('Workspace switching', async () => {
  (apiClient.get as any).mockImplementation((url: string, opts: any) => {
    const ws = opts?.params?.workspace_id
    if (url === '/shortlists') {
      if (ws === 'ws-1') return Promise.resolve({ data: [{ shortlist_id: 's1', job_id: 'j1', candidate_id: 'c1', job_title: 'Job A', candidate_name: 'Alice', current_title: 'Dev', status: 'ACTIVE' }] })
      if (ws === 'ws-2') return Promise.resolve({ data: [{ shortlist_id: 's2', job_id: 'j2', candidate_id: 'c2', job_title: 'Job B', candidate_name: 'Bob', current_title: 'QA', status: 'ACTIVE' }] })
    }
    return Promise.resolve({ data: [] })
  })
  const qc = new QueryClient()
  render(<MemoryRouter><QueryClientProvider client={qc}><Wrapper><ShortlistsPage /></Wrapper></QueryClientProvider></MemoryRouter>)
  await waitFor(() => expect(screen.getByText('Alice')).toBeTruthy())
  act(() => (globalThis as any).__setWs('ws-2'))
  await waitFor(() => expect(screen.getByText('Bob')).toBeTruthy())
  expect(screen.queryByText('Alice')).toBeNull()
})