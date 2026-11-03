import { useState } from 'react'
import axios from 'axios'
import { useAuth } from '../features/auth/AuthContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { Evaluation } from '../features/dashboard/api'
import { apiClient } from '../services/apiClient'
import Sidebar from '../components/layout/Sidebar'
import StyledSelect from '../components/shared/StyledSelect'

export default function EvaluationsPage() {
  const { selectedWorkspace, user } = useAuth()
  const wsId = selectedWorkspace?.workspace_id
  const qc = useQueryClient()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['evaluations', wsId],
    queryFn: async () => (await apiClient.get<Evaluation[]>('/evaluations', { params: { workspace_id: wsId } })).data,
    enabled: !!wsId,
  })
  const [editing, setEditing] = useState<Evaluation | null>(null)
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null)
  const [label, setLabel] = useState<number>(1)
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState<string | null>(null)

  const upsert = useMutation({
    mutationFn: async () => {
      if (!editing) throw new Error('No evaluation selected.')
      const feedback = note.trim()
      return apiClient.put('/evaluations', {
        workspace_id: wsId,
        job_id: editing.job_id,
        candidate_id: editing.candidate_id,
        relevance_label: label,
        review_status: 'reviewed',
        note: feedback || null,
        note_id: feedback ? editingNoteId : null,
        expected_updated_at: editing.updated_at,
      })
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['evaluations', wsId] })
      setMsg('Saved')
      setEditing(null)
      setEditingNoteId(null)
    },
    onError: error => {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        setMsg('This evaluation changed since it was loaded. Refresh and try again.')
      } else if (axios.isAxiosError(error) && error.response?.status === 403) {
        setMsg('You are not authorized to edit this evaluation.')
      } else {
        setMsg('Unable to save evaluation. Please try again.')
      }
    },
  })

  const items = data ?? []
  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <h1 className="page-title">Evaluations</h1>
          </div>

          {msg && <p className={`mb-4 text-sm ${msg === 'Saved' ? 'text-emerald-300' : 'text-red-300'}`}>{msg}</p>}
          {isLoading && <p className="text-slate-300">Loading...</p>}
          {isError && <p className="text-red-300">Failed to load evaluations.</p>}
          {!isLoading && !isError && items.length === 0 && <p className="text-slate-300">No evaluation pairs.</p>}
          {!isLoading && !isError && items.length > 0 && (
            <div className="panel overflow-hidden">
              <table className="table-shell">
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Candidate</th>
                    <th>Status</th>
                    <th>Label</th>
                    <th>Feedback</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(e => (
                    <tr key={`${e.job_id}-${e.candidate_id}-${e.evaluation_id ?? 'pending'}`}>
                      <td className="font-medium text-slate-100">{e.job_title}</td>
                      <td className="text-slate-100">{e.candidate_name}</td>
                      <td><span className="status-pill neutral">{e.review_status}</span></td>
                      <td>{e.relevance_label ?? '-'}</td>
                      <td>{e.notes?.map(existingNote => existingNote.note).join(' · ') || '-'}</td>
                      <td>
                        {(!e.reviewer_id || e.reviewer_id === user?.id) ? (
                          <button
                            type="button"
                            className="button-secondary"
                            onClick={() => {
                              const ownNote = e.notes?.find(existingNote => existingNote.author_id === user?.id)
                              setEditing(e)
                              setEditingNoteId(ownNote?.note_id ?? null)
                              setLabel(e.relevance_label ?? 1)
                              setNote(ownNote?.note ?? '')
                              setMsg(null)
                            }}
                          >
                            Edit
                          </button>
                        ) : (
                          <span className="text-slate-400">Read-only</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {editing && (
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="evaluation-editor-title"
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
            >
              <div className="panel w-full max-w-md p-4 md:p-5">
                <h2 id="evaluation-editor-title" className="section-title">Edit evaluation</h2>
                <div className="space-y-3">
                  <StyledSelect
                    aria-label="Relevance label"
                    value={String(label)}
                    options={[
                      { value: '0', label: '0 - Not relevant' },
                      { value: '1', label: '1 - Partial' },
                      { value: '2', label: '2 - Relevant' },
                    ]}
                    onValueChange={value => setLabel(Number(value))}
                  />
                  <textarea aria-label="Feedback" className="textarea-shell min-h-24" value={note} onChange={e => setNote(e.target.value)} placeholder="Note" />
                  <div className="flex justify-end gap-3">
                    <button type="button" onClick={() => setEditing(null)} className="button-secondary">Cancel</button>
                    <button type="button" onClick={() => upsert.mutate()} className="button-primary">Save</button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}