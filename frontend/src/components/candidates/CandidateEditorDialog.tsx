import { useEffect, useState, type FormEvent } from 'react'
import type { Candidate } from '../../features/dashboard/api'
import type { CandidateInput, CandidateSourceInput, ResumeCandidateDraft } from '../../features/candidates/api'
import { getApiErrorMessage } from '../../lib/apiErrors'
import ModalDialog from '../shared/ModalDialog'

interface CandidateDraft {
  fullName: string
  email: string
  currentTitle: string
  summary: string
  experience: string
  location: string
  skills: string
  sources: CandidateSourceInput[]
}

const emptyDraft = (): CandidateDraft => ({
  fullName: '',
  email: '',
  currentTitle: '',
  summary: '',
  experience: '',
  location: '',
  skills: '',
  sources: [],
})

export function candidateInputFromDraft(draft: CandidateDraft): CandidateInput {
  return {
    full_name: draft.fullName.trim(),
    email: draft.email.trim(),
    current_title: draft.currentTitle.trim() || null,
    summary: draft.summary.trim(),
    experience_years: draft.experience === '' ? null : Number(draft.experience),
    location: draft.location.trim() || null,
    skills: draft.skills.split(',').map(skill => skill.trim()).filter(Boolean),
    sources: draft.sources
      .filter(source => source.provider.trim())
      .map(source => ({
        ...source,
        provider: source.provider.trim(),
        source_url: source.source_url?.trim() || null,
        authorized_basis: source.authorized_basis?.trim() || null,
      })),
  }
}

function draftFromCandidate(candidate?: Candidate): CandidateDraft {
  if (!candidate) return emptyDraft()
  return {
    fullName: candidate.full_name,
    email: candidate.email ?? '',
    currentTitle: candidate.current_title ?? '',
    summary: candidate.summary,
    experience: candidate.experience_years == null ? '' : String(candidate.experience_years),
    location: candidate.location ?? '',
    skills: candidate.skills.map(skill => skill.name).join(', '),
    sources: candidate.sources.map(source => ({
      provider: source.provider,
      source_record_id: source.source_record_id,
      source_url: source.source_url,
      authorized_basis: source.authorized_basis,
    })),
  }
}

function draftFromResumeDraft(candidate?: ResumeCandidateDraft): CandidateDraft {
  if (!candidate) return emptyDraft()
  return {
    fullName: candidate.full_name ?? '',
    email: candidate.email ?? '',
    currentTitle: candidate.current_title ?? '',
    summary: candidate.summary ?? '',
    experience: candidate.experience_years == null ? '' : String(candidate.experience_years),
    location: candidate.location ?? '',
    skills: candidate.skills?.join(', ') ?? '',
    sources: candidate.sources ?? [],
  }
}

export default function CandidateEditorDialog({
  open,
  candidate,
  initialDraft,
  title,
  pending,
  error,
  onClose,
  onSubmit,
}: {
  open: boolean
  candidate?: Candidate
  initialDraft?: ResumeCandidateDraft | null
  title: string
  pending: boolean
  error: unknown
  onClose: () => void
  onSubmit: (input: CandidateInput) => void
}) {
  const [draft, setDraft] = useState(emptyDraft)
  useEffect(() => {
    if (open) setDraft(candidate ? draftFromCandidate(candidate) : draftFromResumeDraft(initialDraft ?? undefined))
  }, [open, candidate?.candidate_id, initialDraft])

  const setField = <K extends keyof CandidateDraft>(key: K, value: CandidateDraft[K]) =>
    setDraft(current => ({ ...current, [key]: value }))
  const setSourceField = <K extends keyof CandidateSourceInput>(
    index: number,
    key: K,
    value: CandidateSourceInput[K],
  ) => setDraft(current => ({
    ...current,
    sources: current.sources.map((source, sourceIndex) =>
      sourceIndex === index ? { ...source, [key]: value } : source,
    ),
  }))
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (draft.experience !== '' && (!Number.isInteger(Number(draft.experience)) || Number(draft.experience) < 0)) return
    onSubmit(candidateInputFromDraft(draft))
  }

  return (
    <ModalDialog open={open} title={title} onClose={onClose}>
      <form className="space-y-4" onSubmit={submit}>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="form-field">
            <span>Full name *</span>
            <input required maxLength={200} className="input-shell" value={draft.fullName} onChange={event => setField('fullName', event.target.value)} />
          </label>
          <label className="form-field">
            <span>Email *</span>
            <input required type="email" maxLength={320} className="input-shell" value={draft.email} onChange={event => setField('email', event.target.value)} />
          </label>
          <label className="form-field">
            <span>Current job title</span>
            <input maxLength={200} className="input-shell" value={draft.currentTitle} onChange={event => setField('currentTitle', event.target.value)} />
          </label>
          <label className="form-field">
            <span>Years of experience</span>
            <input type="number" min="0" step="1" className="input-shell" value={draft.experience} onChange={event => setField('experience', event.target.value)} />
          </label>
          <label className="form-field sm:col-span-2">
            <span>Location</span>
            <input maxLength={200} className="input-shell" value={draft.location} onChange={event => setField('location', event.target.value)} />
          </label>
        </div>
        <label className="form-field">
          <span>Professional summary *</span>
          <textarea required rows={4} className="textarea-shell" value={draft.summary} onChange={event => setField('summary', event.target.value)} />
        </label>
        <label className="form-field">
          <span>Skills</span>
          <input className="input-shell" value={draft.skills} onChange={event => setField('skills', event.target.value)} placeholder="Python, SQL, ..." />
          <span className="text-xs text-slate-400">Separate skills with commas.</span>
        </label>
        <fieldset className="grid gap-3 rounded-xl border border-slate-700/80 p-3 sm:grid-cols-2">
          <legend className="px-1 text-sm font-medium text-slate-300">Profile source</legend>
          {draft.sources.map((source, index) => (
            <div key={index} className="grid gap-3 rounded-xl border border-slate-800 p-3 sm:col-span-2 sm:grid-cols-2">
              <label className="form-field sm:col-span-2">
                <span>Source / provider</span>
                <input maxLength={100} className="input-shell" value={source.provider} onChange={event => setSourceField(index, 'provider', event.target.value)} />
              </label>
              <label className="form-field">
                <span>Profile URL</span>
                <input type="url" maxLength={2000} className="input-shell" value={source.source_url ?? ''} onChange={event => setSourceField(index, 'source_url', event.target.value || null)} />
              </label>
              <label className="form-field">
                <span>Authorized basis</span>
                <input maxLength={500} className="input-shell" value={source.authorized_basis ?? ''} onChange={event => setSourceField(index, 'authorized_basis', event.target.value || null)} />
              </label>
              <div className="flex items-center justify-between gap-3 sm:col-span-2">
                <label className="form-field min-w-0 flex-1">
                  <span>Source record ID</span>
                  <input maxLength={200} className="input-shell" value={source.source_record_id ?? ''} onChange={event => setSourceField(index, 'source_record_id', event.target.value || null)} />
                </label>
                <button
                  type="button"
                  className="button-ghost mt-6 px-3 py-2 text-xs"
                  onClick={() => setDraft(current => ({
                    ...current,
                    sources: current.sources.filter((_item, sourceIndex) => sourceIndex !== index),
                  }))}
                >
                  Remove source
                </button>
              </div>
            </div>
          ))}
          <button
            type="button"
            className="button-ghost justify-self-start text-xs sm:col-span-2"
            onClick={() => setDraft(current => ({
              ...current,
              sources: [...current.sources, {
                provider: '',
                source_record_id: null,
                source_url: null,
                authorized_basis: null,
              }],
            }))}
          >
            Add source
          </button>
        </fieldset>
        {!!error && <p role="alert" className="text-sm text-red-300">{getApiErrorMessage(error, 'Unable to save this candidate.')}</p>}
        <div className="flex flex-wrap justify-end gap-3 pt-1">
          <button type="button" className="button-ghost" disabled={pending} onClick={onClose}>Cancel</button>
          <button type="submit" className="button-primary" disabled={pending}>{pending ? 'Saving...' : 'Save candidate'}</button>
        </div>
      </form>
    </ModalDialog>
  )
}
