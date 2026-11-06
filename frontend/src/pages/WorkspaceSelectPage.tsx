import { ArrowRight, Building2, LogOut } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../features/auth/AuthContext'
import Brand from '../components/shared/Brand'

export default function WorkspaceSelectPage() {
  const { workspaces, selectWorkspace, signOut } = useAuth()
  const navigate = useNavigate()

  if (workspaces.length === 0) {
    return (
      <div className="app-shell flex min-h-screen items-center justify-center p-6">
        <div className="panel max-w-md p-8 text-center">
          <p className="text-lg text-slate-200">No workspaces available.</p>
          <button onClick={signOut} className="button-secondary mt-5 inline-flex items-center gap-2">
            <LogOut size={16} /> Sign out
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell flex min-h-screen items-center justify-center p-6">
      <div className="panel w-full max-w-2xl p-8 md:p-10">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-5">
          <div>
            <Brand size="large" className="mb-6" />
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Workspace</div>
            <h1 className="mt-1 text-3xl font-semibold text-white">Select workspace</h1>
          </div>
          <Building2 aria-hidden="true" size={24} className="text-indigo-300" />
        </div>

        <div className="space-y-3">
          {workspaces.map(w => (
            <button
              key={w.workspace_id}
              onClick={() => { selectWorkspace(w); navigate('/dashboard') }}
              className="group flex w-full items-center justify-between rounded-2xl border border-slate-700 bg-slate-900/70 p-4 text-left transition hover:border-indigo-400/60 hover:bg-slate-800"
            >
              <div>
                <div className="text-lg font-semibold text-slate-50">{w.name}</div>
                <div className="mt-1 text-sm text-slate-400">{w.role}</div>
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <span className="text-xs uppercase tracking-[0.2em] text-slate-500">Open</span>
                <ArrowRight size={18} className="transition group-hover:translate-x-0.5" />
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}