import { useState } from 'react'
import { useAuth } from '../features/auth/AuthContext'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { fetchCandidates } from '../features/dashboard/api'
import Sidebar from '../components/layout/Sidebar'
import SearchField from '../components/shared/SearchField'

export default function CandidatesPage() {
  const { selectedWorkspace } = useAuth()
  const wsId = selectedWorkspace?.workspace_id
  const { data, isLoading, isError } = useQuery({ queryKey: ['candidates', wsId], queryFn: () => fetchCandidates(wsId!), enabled: !!wsId })
  const [q, setQ] = useState('')
  const cands = (data ?? []).filter(c => c.full_name.toLowerCase().includes(q.toLowerCase()))

  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <h1 className="page-title">Candidates</h1>
            <div className="w-full max-w-sm">
              <SearchField label="Search candidates" placeholder="Search candidates" value={q} onChange={setQ} />
            </div>
          </div>

          {isLoading && <p className="text-slate-300">Loading...</p>}
          {isError && <p className="text-red-300">Failed to load candidates.</p>}
          {!isLoading && !isError && cands.length === 0 && <p className="text-slate-300">No candidates found.</p>}
          {!isLoading && !isError && cands.length > 0 && (
            <div className="panel overflow-hidden">
              <table className="table-shell">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Title</th>
                    <th>Location</th>
                  </tr>
                </thead>
                <tbody>
                  {cands.map(c => (
                    <tr key={c.candidate_id}>
                      <td className="font-medium text-slate-100">
                        <Link className="text-indigo-200 underline-offset-4 hover:text-white hover:underline" to={`/candidates/${c.candidate_id}`}>
                          {c.full_name}
                        </Link>
                      </td>
                      <td className="text-slate-300">{c.current_title ?? '—'}</td>
                      <td className="text-slate-400">{c.location ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

        </div>
      </main>
    </div>
  )
}