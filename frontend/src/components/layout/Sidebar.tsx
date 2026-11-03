import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Briefcase, Users, Search, Filter, Star, ClipboardCheck, Settings, PanelLeftClose, PanelLeftOpen, Sparkles, LogOut } from 'lucide-react'
import { useAuth } from '../../features/auth/AuthContext'
import StyledSelect from '../shared/StyledSelect'

const links = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/jobs', label: 'Jobs', icon: Briefcase },
  { to: '/candidates', label: 'Candidates', icon: Users },
  { to: '/matching', label: 'Matching', icon: Search },
  { to: '/boolean-search', label: 'Boolean Search', icon: Filter },
  { to: '/shortlisted', label: 'Shortlisted', icon: Star },
  { to: '/evaluations', label: 'Evaluations', icon: ClipboardCheck },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const [confirmSignOut, setConfirmSignOut] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const { selectedWorkspace, workspaces, selectWorkspace, signOut } = useAuth()
  const navigate = useNavigate()
  const workspaceOptions = workspaces ?? []

  const handleSignOut = async () => {
    setSigningOut(true)
    try {
      await signOut()
      navigate('/login', { replace: true })
      setConfirmSignOut(false)
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <aside className={`${collapsed ? 'w-16' : 'w-16 sm:w-56 md:w-72'} sticky top-0 left-0 h-screen shrink-0 border-r border-slate-800/80 bg-slate-950/80 backdrop-blur-xl`}>
      <div className="flex h-full flex-col p-3">
        <div className={`mb-5 flex items-center justify-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 ${collapsed ? 'flex-col px-0 py-2' : 'px-2 py-3 sm:justify-between sm:px-3'}`}>
          <div className="flex min-w-0 items-center gap-3 overflow-hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-400 text-slate-950 shadow-lg shadow-indigo-500/30">
              <Sparkles size={18} />
            </div>
            {!collapsed && (
              <div className="hidden min-w-0 sm:block">
                <div className="text-sm font-semibold tracking-[0.25em] text-slate-400 uppercase">Apex</div>
                <div className="text-base font-semibold text-slate-100">Recruit</div>
              </div>
            )}
          </div>
          <button
            type="button"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            onClick={() => setCollapsed(v => !v)}
            className={`${collapsed ? 'mx-auto' : 'ml-auto'} hidden rounded-lg border border-slate-700 bg-slate-900 p-2 text-slate-300 transition hover:border-slate-500 hover:text-white sm:inline-flex`}
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>

        <nav className="space-y-1.5 px-1">
          {links.map(link => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/dashboard'}
              aria-label={link.label}
              title={link.label}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                  isActive
                    ? 'bg-gradient-to-r from-indigo-500/20 to-cyan-500/10 text-white ring-1 ring-inset ring-indigo-400/50'
                    : 'text-slate-300 hover:bg-slate-800/80 hover:text-white'
                } ${collapsed ? 'h-10 w-10 shrink-0 justify-center p-0' : 'justify-center sm:justify-start'}`
              }
            >
              <link.icon size={collapsed ? 21 : 17} className="shrink-0" />
              <span className={collapsed ? 'sr-only' : 'hidden sm:inline'}>{link.label}</span>
            </NavLink>
          ))}
        </nav>

        <button
          type="button"
          aria-label="Sign Out"
          title="Sign Out"
          onClick={() => setConfirmSignOut(true)}
          className={`mb-3 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-700 px-2 py-2.5 text-sm font-medium text-slate-300 transition hover:border-rose-400/50 hover:bg-rose-500/10 hover:text-rose-100 ${collapsed ? 'sm:px-0' : 'sm:px-3 sm:justify-start'}`}
        >
          <LogOut size={17} />
          {!collapsed && <span className="hidden sm:inline">Sign Out</span>}
        </button>

        <div className={`mt-auto rounded-2xl border border-indigo-500/25 bg-gradient-to-br from-indigo-500/10 via-slate-900/90 to-cyan-500/10 text-left ${collapsed ? 'p-1' : 'p-1 sm:p-3'}`}>
          {!collapsed && (
            <div className="hidden sm:block">
              <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-indigo-300">Workspace</div>
            </div>
          )}
          <StyledSelect
            aria-label="Workspace"
            title={selectedWorkspace?.name ?? 'Workspace'}
            className={`mt-2 px-2 py-2 text-xs ${collapsed ? 'sm:mt-0 select-trigger-compact' : ''}`}
            value={selectedWorkspace?.workspace_id ?? ''}
            placeholder={workspaceOptions.length === 0 ? 'No workspace selected' : 'Select workspace'}
            options={workspaceOptions.map(workspace => ({
              value: workspace.workspace_id,
              label: workspace.name,
            }))}
            disabled={workspaceOptions.length === 0}
            onValueChange={value => {
              const workspace = workspaceOptions.find(item => item.workspace_id === value)
              if (workspace) selectWorkspace(workspace)
            }}
          />
          {selectedWorkspace && !collapsed && (
            <div className="mt-1 hidden text-xs text-slate-400 sm:block">{selectedWorkspace.role}</div>
          )}
        </div>
      </div>
      {confirmSignOut && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4">
          <section
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="sign-out-title"
            aria-describedby="sign-out-description"
            className="panel w-full max-w-sm p-6"
          >
            <h2 id="sign-out-title" className="text-lg font-semibold text-slate-100">Sign out?</h2>
            <p id="sign-out-description" className="mt-2 text-sm text-slate-300">
              You will need to sign in again to access this workspace.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                className="button-ghost"
                disabled={signingOut}
                onClick={() => setConfirmSignOut(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="button-secondary inline-flex items-center gap-2"
                disabled={signingOut}
                onClick={() => void handleSignOut()}
              >
                <LogOut size={16} />
                {signingOut ? 'Signing out...' : 'Sign Out'}
              </button>
            </div>
          </section>
        </div>
      )}
    </aside>
  )
}