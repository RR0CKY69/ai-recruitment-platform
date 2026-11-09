import { useEffect, useState } from 'react'
import { LogOut } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../features/auth/AuthContext'
import { readCompactTablesPreference, saveCompactTablesPreference } from '../features/settings/preferences'
import Sidebar from '../components/layout/Sidebar'
import ConfirmationDialog from '../components/shared/ConfirmationDialog'

export default function SettingsPage() {
  const { user, selectedWorkspace, signOut } = useAuth()
  const navigate = useNavigate()
  const [preference, setPreference] = useState(() => {
    try {
      return { compactTables: readCompactTablesPreference(), error: null as string | null }
    } catch {
      return {
        compactTables: false,
        error: 'Could not load this browser preference. Check browser storage permissions and try again.',
      }
    }
  })
  const { compactTables, error: preferenceError } = preference
  const [confirmSignOut, setConfirmSignOut] = useState(false)
  const [signingOut, setSigningOut] = useState(false)

  useEffect(() => {
    const root = document.getElementById('root')
    if (root) root.dataset.compactTables = String(compactTables)
  }, [compactTables])

  const updateCompactTables = (enabled: boolean) => {
    try {
      saveCompactTablesPreference(enabled)
      setPreference({ compactTables: enabled, error: null })
    } catch {
      setPreference(current => ({
        ...current,
        error: 'Could not save this browser preference. Check browser storage permissions and try again.',
      }))
    }
  }

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
    <div className="app-shell flex">
      <Sidebar />
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">Account</p>
              <h1 className="page-title">Settings</h1>
            </div>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <section className="panel p-4 md:p-5" aria-labelledby="account-settings-heading">
              <h2 id="account-settings-heading" className="section-title">Account / Profile</h2>
              <dl className="space-y-4">
                <SettingValue label="Name" value={user?.full_name ?? 'Unavailable'} />
                <SettingValue label="Email" value={user?.email ?? 'Unavailable'} />
                <SettingValue label="Account status" value={user?.is_active ? 'Active' : 'Inactive'} />
                <SettingValue label="Account-wide role" value="Not defined by the current account model" />
              </dl>
              <p className="mt-4 text-xs text-slate-400">
                Profile changes are unavailable because the API does not provide an account update endpoint.
              </p>
            </section>

            <section className="panel p-4 md:p-5" aria-labelledby="workspace-settings-heading">
              <h2 id="workspace-settings-heading" className="section-title">Workspace</h2>
              {selectedWorkspace ? (
                <dl className="space-y-4">
                  <SettingValue label="Workspace name" value={selectedWorkspace.name} />
                  <SettingValue label="Workspace slug" value={selectedWorkspace.slug} />
                  <SettingValue label="Your workspace role" value={selectedWorkspace.role} />
                </dl>
              ) : (
                <p className="text-sm text-slate-300">No workspace is selected.</p>
              )}
              <p className="mt-4 text-xs text-slate-400">
                Manage your workspace name and team membership from the Workspace & Team page. Your permissions depend on your workspace role.
              </p>
            </section>

            <section className="panel p-4 md:p-5" aria-labelledby="preferences-heading">
              <h2 id="preferences-heading" className="section-title">Application Preferences</h2>
              <label className="flex items-start gap-3 text-sm text-slate-200">
                <input
                  type="checkbox"
                  className="mt-1 accent-indigo-500"
                  checked={compactTables}
                  onChange={event => updateCompactTables(event.target.checked)}
                />
                <span>
                  <span className="block font-medium">Compact table rows</span>
                  <span className="mt-1 block text-xs text-slate-400">Use less vertical space in application tables.</span>
                </span>
              </label>
              <p className="mt-4 text-xs text-slate-400">Preferences are saved only in this browser and are not sent to the server.</p>
              {preferenceError && <p role="alert" className="mt-3 text-sm text-red-300">{preferenceError}</p>}
            </section>

            <section className="panel p-4 md:p-5" aria-labelledby="security-settings-heading">
              <h2 id="security-settings-heading" className="section-title">Security / Session</h2>
              <dl className="space-y-4">
                <SettingValue label="Signed-in account" value={user?.email ?? 'Unavailable'} />
                <SettingValue label="Access token storage" value="In memory only" />
                <SettingValue label="Refresh session" value="Managed by the server using an HttpOnly cookie" />
              </dl>
              <p className="mt-4 text-xs text-slate-400">
                Session expiry and device details are not exposed by the current API.
              </p>
              <button
                type="button"
                className="button-secondary mt-5 inline-flex items-center gap-2"
                onClick={() => setConfirmSignOut(true)}
              >
                <LogOut size={16} />
                Sign Out
              </button>
            </section>
          </div>
        </div>
      </main>

      <ConfirmationDialog
        open={confirmSignOut}
        title="Sign out?"
        description="Your server refresh session will be revoked."
        confirmLabel="Sign Out"
        confirmingLabel="Signing out..."
        confirming={signingOut}
        onCancel={() => setConfirmSignOut(false)}
        onConfirm={() => void handleSignOut()}
      />
    </div>
  )
}

function SettingValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-1 break-words text-sm text-slate-100">{value}</dd>
    </div>
  )
}
