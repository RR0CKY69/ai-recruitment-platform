import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Briefcase,
  Users,
  Search,
  Filter,
  Star,
  ClipboardCheck,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  GitBranch,
  Building2,
  LogOut,
} from 'lucide-react'
import { useAuth } from '../../features/auth/AuthContext'
import StyledSelect from '../shared/StyledSelect'
import Brand from '../shared/Brand'
import ConfirmationDialog from '../shared/ConfirmationDialog'

const groups = [
  {
    label: 'Workspace',
    links: [
      { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/jobs', label: 'Jobs', icon: Briefcase },
      { to: '/candidates', label: 'Candidates', icon: Users },
    ],
  },
  {
    label: 'Recruitment',
    links: [
      { to: '/matching', label: 'Matching', icon: Search },
      { to: '/evaluations', label: 'Evaluations', icon: ClipboardCheck },
      { to: '/shortlisted', label: 'Shortlisted', icon: Star },
      { to: '/pipeline', label: 'Pipeline', icon: GitBranch },
    ],
  },
  {
    label: 'Sourcing',
    links: [{ to: '/boolean-search', label: 'Boolean Search', icon: Filter }],
  },
  {
    label: 'Administration',
    links: [
      { to: '/settings', label: 'Settings', icon: Settings },
      { to: '/workspace-team', label: 'Workspace & Team', icon: Building2 },
    ],
  },
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
    <aside className={`${collapsed ? 'w-16' : 'w-16 sm:w-56 md:w-72'} sticky top-0 left-0 h-screen shrink-0 overflow-x-hidden border-r border-slate-800/80 bg-slate-950/80 backdrop-blur-xl`}>
      <div className={`flex h-full flex-col ${collapsed ? 'p-1' : 'p-1 sm:p-3'}`}>
        <div className={`mb-5 flex items-center justify-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 ${collapsed ? 'flex-col px-0 py-2' : 'px-2 py-3 sm:justify-between sm:px-3'}`}>
          <Brand showName={!collapsed} nameClassName="hidden sm:block" />
          <button
            type="button"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            onClick={() => setCollapsed(v => !v)}
            className={`${collapsed ? 'mx-auto' : 'ml-auto'} hidden rounded-lg border border-slate-700 bg-slate-900 p-2 text-slate-300 transition hover:border-slate-500 hover:text-white sm:inline-flex`}
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>

        <nav aria-label="Primary navigation" className="min-h-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto px-0 sm:px-1">
          {groups.map(group => (
            <section key={group.label} aria-labelledby={`navigation-${group.label.toLowerCase()}`}>
              <h2
                id={`navigation-${group.label.toLowerCase()}`}
                className={collapsed
                  ? 'sr-only'
                  : 'mb-1 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500 max-sm:sr-only'}
              >
                {group.label}
              </h2>
              <div className="space-y-1">
                {group.links.map(link => (
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
                    <link.icon size={collapsed ? 21 : 17} className="shrink-0" aria-hidden="true" />
                    <span className={collapsed ? 'sr-only' : 'hidden sm:inline'}>{link.label}</span>
                  </NavLink>
                ))}
              </div>
            </section>
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
      <ConfirmationDialog
        open={confirmSignOut}
        title="Sign out?"
        description="You will need to sign in again to access this workspace."
        confirmLabel="Sign Out"
        confirmingLabel="Signing out..."
        confirming={signingOut}
        onCancel={() => setConfirmSignOut(false)}
        onConfirm={() => void handleSignOut()}
      />
    </aside>
  )
}