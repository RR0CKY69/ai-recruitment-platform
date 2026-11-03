import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../features/auth/AuthContext'
import { useQuery } from '@tanstack/react-query'
import { fetchJobs } from '../features/dashboard/api'
import Sidebar from '../components/layout/Sidebar'
import SearchField from '../components/shared/SearchField'

export default function JobsPage() {
  const { selectedWorkspace } = useAuth()
  const wsId = selectedWorkspace?.workspace_id
  const { data, isLoading, isError } = useQuery({ queryKey: ['jobs', wsId], queryFn: () => fetchJobs(wsId!), enabled: !!wsId })
  const [q, setQ] = useState('')
  const jobs = (data ?? []).filter(j => j.title.toLowerCase().includes(q.toLowerCase()))

  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <h1 className="page-title">Jobs</h1>
            <div className="w-full max-w-sm">
              <SearchField label="Search jobs" placeholder="Search jobs" value={q} onChange={setQ} />
            </div>
          </div>

          {isLoading && <p className="text-slate-300">Loading...</p>}
          {isError && <p className="text-red-300">Failed to load jobs.</p>}
          {!isLoading && !isError && jobs.length === 0 && <p className="text-slate-300">No jobs found.</p>}
          {!isLoading && !isError && jobs.length > 0 && (
            <div className="panel overflow-hidden">
              <table className="table-shell">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Location</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map(j => (
                    <tr key={j.job_id}>
                      <td className="font-medium text-slate-100">
                        <Link className="text-indigo-200 underline-offset-4 hover:text-white hover:underline" to={`/jobs/${j.job_id}`}>
                          {j.title}
                        </Link>
                      </td>
                      <td><span className="status-pill neutral">{j.status}</span></td>
                      <td className="text-slate-400">{j.location ?? '—'}</td>
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