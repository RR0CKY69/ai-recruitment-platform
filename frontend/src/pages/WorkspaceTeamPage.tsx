import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Building2, PencilLine, Plus, Trash2 } from 'lucide-react'
import { useAuth } from '../features/auth/AuthContext'
import {
  addWorkspaceMember,
  fetchWorkspace,
  fetchWorkspaceMembers,
  removeWorkspaceMember,
  updateWorkspace,
  updateWorkspaceMemberRole,
  type WorkspaceMember,
  type WorkspaceRole,
} from '../features/workspaces/api'
import { getApiErrorMessage } from '../lib/apiErrors'
import Sidebar from '../components/layout/Sidebar'
import ModalDialog from '../components/shared/ModalDialog'
import ConfirmationDialog from '../components/shared/ConfirmationDialog'
import {
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
} from '../components/shared/Primitives'
import StyledSelect from '../components/shared/StyledSelect'

export default function WorkspaceTeamPage() {
  const {
    user,
    selectedWorkspace,
    updateWorkspaceInContext,
    removeWorkspaceFromContext,
  } = useAuth()
  const navigate = useNavigate()
  const workspaceId = selectedWorkspace?.workspace_id
  const queryClient = useQueryClient()

  const [editingName, setEditingName] = useState(false)
  const [addingMember, setAddingMember] = useState(false)
  const [removingMember, setRemovingMember] = useState<WorkspaceMember | null>(null)
  const [workspaceName, setWorkspaceName] = useState('')
  const [memberEmail, setMemberEmail] = useState('')
  const [memberRole, setMemberRole] = useState<WorkspaceRole>('RECRUITER')

  const workspaceQuery = useQuery({
    queryKey: ['workspace', workspaceId],
    queryFn: () => fetchWorkspace(workspaceId!),
    enabled: !!workspaceId,
  })

  const membersQuery = useQuery({
    queryKey: ['workspace-members', workspaceId],
    queryFn: () => fetchWorkspaceMembers(workspaceId!),
    enabled: !!workspaceId,
  })

  const isAdmin = (workspaceQuery.data ?? selectedWorkspace)?.role === 'ADMIN'

  const refreshWorkspaceData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['workspace', workspaceId] }),
      queryClient.invalidateQueries({ queryKey: ['workspace-members', workspaceId] }),
      queryClient.invalidateQueries({ queryKey: ['workspaces'] }),
    ])
  }

  const updateNameMutation = useMutation({
    mutationFn: (name: string) => updateWorkspace(workspaceId!, { name }),
    onSuccess: async updated => {
      if (selectedWorkspace) {
        const updatedWorkspace = {
          ...selectedWorkspace,
          name: updated.name,
          slug: updated.slug,
        }

        updateWorkspaceInContext(updatedWorkspace)
        queryClient.setQueryData(['workspace', workspaceId], updatedWorkspace)
        queryClient.setQueryData(
          ['workspaces'],
          (current: typeof selectedWorkspace[] | undefined) =>
            current?.map(workspace =>
              workspace.workspace_id === updated.workspace_id
                ? updatedWorkspace
                : workspace
            )
        )
      }

      await refreshWorkspaceData()
      setEditingName(false)
    },
  })

  const addMemberMutation = useMutation({
    mutationFn: () => addWorkspaceMember(workspaceId!, {
      email: memberEmail.trim(),
      role: memberRole,
    }),
    onSuccess: async () => {
      await refreshWorkspaceData()
      setAddingMember(false)
      setMemberEmail('')
      setMemberRole('RECRUITER')
    },
  })

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: WorkspaceRole }) =>
      updateWorkspaceMemberRole(workspaceId!, userId, { role }),
    onSuccess: async (updated, variables) => {
      if (variables.userId === user?.id && selectedWorkspace) {
        queryClient.setQueryData(
          ['workspace', workspaceId],
          (current: typeof selectedWorkspace | undefined) =>
            current ? { ...current, role: updated.role } : current,
        )
        updateWorkspaceInContext({ ...selectedWorkspace, role: updated.role })
      }
      await refreshWorkspaceData()
    },
  })

  const removeMutation = useMutation({
    mutationFn: (userId: string) => removeWorkspaceMember(workspaceId!, userId),
    onSuccess: async (_result, userId) => {
      setRemovingMember(null)

      if (userId === user?.id && workspaceId) {
        queryClient.removeQueries({ queryKey: ['workspace', workspaceId] })
        queryClient.removeQueries({ queryKey: ['workspace-members', workspaceId] })
        removeWorkspaceFromContext(workspaceId)
        navigate('/workspaces', { replace: true })
        return
      }

      await refreshWorkspaceData()
    },
  })

  const workspace = workspaceQuery.data
  const members = membersQuery.data ?? []

  const handleNameSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const name = workspaceName.trim()
    if (!name) return
    updateNameMutation.mutate(name)
  }

  const handleAddMember = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!memberEmail.trim()) return
    addMemberMutation.mutate()
  }

  const openNameEditor = () => {
    setWorkspaceName(workspace?.name ?? selectedWorkspace?.name ?? '')
    updateNameMutation.reset()
    setEditingName(true)
  }

  const openAddMember = () => {
    addMemberMutation.reset()
    setMemberEmail('')
    setMemberRole('RECRUITER')
    setAddingMember(true)
  }

  return (
    <div className="app-shell flex">
      <Sidebar />

      <main className="min-w-0 flex-1 p-4 md:p-6">
        <div className="page-shell">
          <header className="page-header">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">
                Administration
              </p>
              <h1 className="page-title">Workspace & Team</h1>
              <p className="mt-2 text-sm text-slate-400">
                Manage workspace settings, members, and access permissions.
              </p>
            </div>

            {isAdmin && (
              <button
                type="button"
                className="button-primary inline-flex items-center justify-center gap-2"
                onClick={openAddMember}
                disabled={!workspaceId}
              >
                <Plus size={17} aria-hidden="true" />
                Add member
              </button>
            )}
          </header>

          {!workspaceId && (
            <EmptyState
              title="No workspace selected"
              description="Select a workspace from the sidebar to manage its details and members."
            />
          )}

          {workspaceId && workspaceQuery.isLoading && (
            <LoadingState label="Loading workspace details..." />
          )}

          {workspaceId && workspaceQuery.isError && (
            <ErrorState
              title="Unable to load workspace"
              description={getApiErrorMessage(workspaceQuery.error, 'Please try again.')}
            />
          )}

          {workspaceId && workspace && (
            <section className="panel mb-6 p-4 md:p-6" aria-labelledby="workspace-overview-heading">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex min-w-0 items-start gap-3">
                  <div className="rounded-xl border border-indigo-400/20 bg-indigo-400/10 p-3">
                    <Building2 size={23} className="text-indigo-200" aria-hidden="true" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                      Current workspace
                    </p>
                    <h2 id="workspace-overview-heading" className="mt-1 break-words text-xl font-semibold text-white">
                      {workspace.name}
                    </h2>
                    <p className="mt-1 text-sm text-slate-400">
                      Slug: {workspace.slug}
                    </p>
                  </div>
                </div>

                {isAdmin && (
                  <button
                    type="button"
                    className="button-secondary inline-flex items-center gap-2"
                    onClick={openNameEditor}
                  >
                    <PencilLine size={15} aria-hidden="true" />
                    Edit name
                  </button>
                )}
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-slate-700/80 bg-slate-900/50 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Your role</p>
                  <div className="mt-2">
                    <StatusBadge
                      label={workspace.role}
                      tone={workspace.role === 'ADMIN' ? 'info' : 'neutral'}
                    />
                  </div>
                </div>

                <div className="rounded-xl border border-slate-700/80 bg-slate-900/50 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Team members</p>
                  <p className="mt-2 text-xl font-semibold tabular-nums text-white">
                    {membersQuery.data?.length ?? '—'}
                  </p>
                </div>
              </div>
            </section>
          )}

          {workspaceId && (
            <section aria-labelledby="team-members-heading">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 id="team-members-heading" className="section-title">Team members</h2>
                  <p className="mt-1 text-sm text-slate-400">
                    People who have access to this workspace.
                  </p>
                </div>
                <span className="text-xs text-slate-400">
                  {members.length} {members.length === 1 ? 'member' : 'members'}
                </span>
              </div>

              {membersQuery.isLoading && (
                <LoadingState label="Loading team members..." />
              )}

              {membersQuery.isError && (
                <ErrorState
                  title="Unable to load team members"
                  description={getApiErrorMessage(membersQuery.error, 'Please try again.')}
                />
              )}

              {roleMutation.isError && (
                <div className="mb-4">
                  <ErrorState
                    title="Unable to update member role"
                    description={getApiErrorMessage(roleMutation.error, 'Please try again.')}
                  />
                </div>
              )}


              {!membersQuery.isLoading && !membersQuery.isError && members.length === 0 && (
                <EmptyState
                  title="No team members"
                  description="There are currently no members in this workspace."
                  action={isAdmin ? (
                    <button type="button" className="button-primary" onClick={openAddMember}>
                      Add your first member
                    </button>
                  ) : undefined}
                />
              )}

              {!membersQuery.isLoading && !membersQuery.isError && members.length > 0 && (
                <div className="panel overflow-hidden">
                  <div className="table-scroll">
                    <table className="table-shell">
                      <thead>
                        <tr>
                          <th>Member</th>
                          <th>Role</th>
                          <th>Joined</th>
                          {isAdmin && <th><span className="sr-only">Actions</span></th>}
                        </tr>
                      </thead>
                      <tbody>
                        {members.map(member => (
                          <tr key={member.membership_id}>
                            <td>
                              <div className="font-medium text-slate-100">{member.full_name}</div>
                              <div className="mt-1 text-xs text-slate-400">{member.email}</div>
                              {member.user_id === user?.id && (
                                <span className="mt-1 inline-block text-xs text-indigo-300">You</span>
                              )}
                            </td>
                            <td>
                              {isAdmin ? (
                                <StyledSelect
                                  aria-label={`Role for ${member.full_name}`}
                                  className="min-w-32 py-2 text-xs"
                                  value={member.role}
                                  disabled={roleMutation.isPending}
                                  options={[
                                    { value: 'ADMIN', label: 'ADMIN' },
                                    { value: 'RECRUITER', label: 'RECRUITER' },
                                  ]}
                                  onValueChange={value => {
                                    const role = value as WorkspaceRole
                                    if (role !== member.role) {
                                      roleMutation.reset()
                                      roleMutation.mutate({ userId: member.user_id, role })
                                    }
                                  }}
                                />
                              ) : (
                                <StatusBadge
                                  label={member.role}
                                  tone={member.role === 'ADMIN' ? 'info' : 'neutral'}
                                />
                              )}
                            </td>
                            <td className="whitespace-nowrap text-sm text-slate-400">
                              {new Date(member.created_at).toLocaleDateString()}
                            </td>
                            {isAdmin && (
                              <td>
                                <button
                                  type="button"
                                  className="button-ghost inline-flex items-center gap-2 px-3 py-2 text-xs text-rose-300 hover:text-rose-200"
                                  aria-label={`Remove ${member.full_name}`}
                                  disabled={removeMutation.isPending}
                                  onClick={() => {
                                    removeMutation.reset()
                                    setRemovingMember(member)
                                  }}
                                >
                                  <Trash2 size={14} aria-hidden="true" />
                                  Remove
                                </button>
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </section>
          )}
        </div>
      </main>

      <ModalDialog
        open={editingName}
        title="Edit workspace name"
        description="Change the name displayed throughout this workspace."
        onClose={() => {
          if (!updateNameMutation.isPending) setEditingName(false)
        }}
      >
        <form className="space-y-4" onSubmit={handleNameSubmit}>
          <label className="form-field">
            <span>Workspace name *</span>
            <input
              autoFocus
              required
              maxLength={200}
              className="input-shell"
              value={workspaceName}
              onChange={event => setWorkspaceName(event.target.value)}
            />
          </label>

          {updateNameMutation.isError && (
            <ErrorState
              title="Unable to update workspace"
              description={getApiErrorMessage(updateNameMutation.error, 'Please try again.')}
            />
          )}

          <div className="flex justify-end gap-3">
            <button
              type="button"
              className="button-ghost"
              disabled={updateNameMutation.isPending}
              onClick={() => setEditingName(false)}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="button-primary"
              disabled={updateNameMutation.isPending || !workspaceName.trim()}
            >
              {updateNameMutation.isPending ? 'Saving...' : 'Save changes'}
            </button>
          </div>
        </form>
      </ModalDialog>

      <ModalDialog
        open={addingMember}
        title="Add team member"
        description="Add an existing active user by their registered email address."
        onClose={() => {
          if (!addMemberMutation.isPending) setAddingMember(false)
        }}
      >
        <form className="space-y-4" onSubmit={handleAddMember}>
          <label className="form-field">
            <span>Email address *</span>
            <input
              autoFocus
              type="email"
              required
              maxLength={320}
              className="input-shell"
              placeholder="person@example.com"
              value={memberEmail}
              onChange={event => setMemberEmail(event.target.value)}
            />
          </label>

          <label className="form-field">
            <span>Workspace role</span>
            <StyledSelect
              value={memberRole}
              options={[
                { value: 'RECRUITER', label: 'RECRUITER' },
                { value: 'ADMIN', label: 'ADMIN' },
              ]}
              onValueChange={value => setMemberRole(value as WorkspaceRole)}
            />
          </label>

          <p className="text-xs leading-5 text-slate-400">
            The user must already have an active account. This action does not send an invitation email.
          </p>

          {addMemberMutation.isError && (
            <ErrorState
              title="Unable to add member"
              description={getApiErrorMessage(addMemberMutation.error, 'Please check the email and try again.')}
            />
          )}

          <div className="flex justify-end gap-3">
            <button
              type="button"
              className="button-ghost"
              disabled={addMemberMutation.isPending}
              onClick={() => setAddingMember(false)}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="button-primary"
              disabled={addMemberMutation.isPending || !memberEmail.trim()}
            >
              {addMemberMutation.isPending ? 'Adding...' : 'Add member'}
            </button>
          </div>
        </form>
      </ModalDialog>

      <ConfirmationDialog
        open={!!removingMember}
        title="Remove team member?"
        description={
          removingMember
            ? `Remove ${removingMember.full_name} (${removingMember.email}) from this workspace? They will lose access to its jobs, candidates, and other workspace data.`
            : ''
        }
        confirmLabel="Remove member"
        confirmingLabel="Removing..."
        confirming={removeMutation.isPending}
        error={
          removeMutation.isError
            ? getApiErrorMessage(removeMutation.error, 'Please try again.')
            : undefined
        }
        onCancel={() => {
          setRemovingMember(null)
          removeMutation.reset()
        }}
        onConfirm={() => {
          if (removingMember) removeMutation.mutate(removingMember.user_id)
        }}
      />
    </div>
  )
}
