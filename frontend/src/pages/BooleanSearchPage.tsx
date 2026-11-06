import { useMemo, useState } from 'react'
import { Copy, RotateCcw, Wand2 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../features/auth/AuthContext'
import { fetchJobs } from '../features/dashboard/api'
import { generateBooleanQuery, splitKeywords } from '../features/booleanSearch/query'
import type { BooleanOperator, BooleanSearchTemplate } from '../features/booleanSearch/query'
import Sidebar from '../components/layout/Sidebar'
import StyledSelect from '../components/shared/StyledSelect'

export default function BooleanSearchPage() {
  const { selectedWorkspace } = useAuth()
  const workspaceId = selectedWorkspace?.workspace_id
  const jobsQuery = useQuery({
    queryKey: ['jobs', workspaceId],
    queryFn: () => fetchJobs(workspaceId!),
    enabled: !!workspaceId,
  })
  const [jobId, setJobId] = useState('')
  const [includeText, setIncludeText] = useState('')
  const [excludeText, setExcludeText] = useState('')
  const [operator, setOperator] = useState<BooleanOperator>('OR')
  const [template, setTemplate] = useState<BooleanSearchTemplate>('linkedin')
  const [queryDraft, setQueryDraft] = useState<{ source: string; value: string } | null>(null)
  const [copyMessage, setCopyMessage] = useState<string | null>(null)

  const selectedJob = jobsQuery.data?.find(job => job.job_id === jobId)
  const generated = useMemo(() => selectedJob ? generateBooleanQuery({
    title: selectedJob.title,
    description: selectedJob.description,
    requiredSkills: selectedJob.required_skills,
    includeKeywords: splitKeywords(includeText),
    excludeKeywords: splitKeywords(excludeText),
    includeOperator: operator,
    template,
  }) : '', [selectedJob, includeText, excludeText, operator, template])
  const query = queryDraft && queryDraft.source === generated ? queryDraft.value : generated
  const hasManualOverride = queryDraft !== null && queryDraft.source === generated && queryDraft.value !== generated

  const resetFields = () => {
    setIncludeText('')
    setExcludeText('')
    setOperator('OR')
    setTemplate('linkedin')
    setQueryDraft(null)
    setCopyMessage(null)
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(query)
      setCopyMessage('Query copied to clipboard.')
    } catch {
      setCopyMessage('Could not access the clipboard. Select and copy the query manually.')
    }
  }

  return (
    <div className="app-shell flex">
      <Sidebar />
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <div className="page-shell">
          <div className="page-header">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">Sourcing tools</p>
              <h1 className="page-title">Boolean Search</h1>
            </div>
          </div>

          <section className="panel max-w-4xl p-4 md:p-5" aria-label="Boolean query builder">
            <div className="space-y-4">
              <div>
                <label htmlFor="boolean-job" className="mb-2 block text-sm font-medium text-slate-300">Workspace job</label>
                <StyledSelect
                  id="boolean-job"
                  aria-label="Workspace job"
                  value={jobId}
                  placeholder="Select a job"
                  disabled={jobsQuery.isLoading || jobsQuery.isError}
                  options={(jobsQuery.data ?? []).map(job => ({ value: job.job_id, label: job.title }))}
                  onValueChange={value => {
                    setJobId(value)
                    setIncludeText('')
                    setExcludeText('')
                    setQueryDraft(null)
                    setCopyMessage(null)
                  }}
                />
              </div>
              {jobsQuery.isLoading && <p role="status" className="text-sm text-slate-300">Loading workspace jobs...</p>}
              {jobsQuery.isError && <p role="alert" className="text-sm text-red-300">Failed to load workspace jobs.</p>}

              {!jobsQuery.isLoading && !jobsQuery.isError && !selectedJob && (
                <p className="rounded-xl border border-slate-700/70 bg-slate-900/50 p-4 text-sm text-slate-300">
                  Select a job to review its details and generate a Boolean query.
                </p>
              )}

              {selectedJob && (
                <>
                  <div className="rounded-xl border border-slate-700/70 bg-slate-900/50 p-4">
                    <h2 className="font-semibold text-slate-100">{selectedJob.title}</h2>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-slate-300">
                      {selectedJob.description || 'No job description available.'}
                    </p>
                    <p className="mt-3 text-sm text-slate-300">
                      Requirements: {selectedJob.required_skills.length > 0 ? selectedJob.required_skills.join(', ') : 'Not specified'}
                    </p>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <KeywordField
                      id="boolean-include"
                      label="Include keywords"
                      placeholder="e.g. Django, FastAPI"
                      value={includeText}
                      onChange={value => {
                        setIncludeText(value)
                        setQueryDraft(null)
                        setCopyMessage(null)
                      }}
                    />
                    <KeywordField
                      id="boolean-exclude"
                      label="Exclude keywords"
                      placeholder="e.g. Intern, Junior"
                      value={excludeText}
                      onChange={value => {
                        setExcludeText(value)
                        setQueryDraft(null)
                        setCopyMessage(null)
                      }}
                    />
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label htmlFor="boolean-operator" className="mb-2 block text-sm font-medium text-slate-300">Included keyword logic</label>
                      <StyledSelect
                        id="boolean-operator"
                        aria-label="Included keyword logic"
                        value={operator}
                        placeholder="Select keyword logic"
                        options={[
                          { value: 'OR', label: 'Match any (OR)' },
                          { value: 'AND', label: 'Match all (AND)' },
                        ]}
                        onValueChange={value => {
                          setOperator(value as BooleanOperator)
                          setQueryDraft(null)
                          setCopyMessage(null)
                        }}
                      />
                    </div>
                    <div>
                      <label htmlFor="boolean-template" className="mb-2 block text-sm font-medium text-slate-300">Query template</label>
                      <StyledSelect
                        id="boolean-template"
                        aria-label="Query template"
                        value={template}
                        placeholder="Select a template"
                        options={[
                          { value: 'linkedin', label: 'LinkedIn' },
                          { value: 'google_xray', label: 'Google / X-ray' },
                          { value: 'job_board', label: 'General job board' },
                        ]}
                        onValueChange={value => {
                          setTemplate(value as BooleanSearchTemplate)
                          setQueryDraft(null)
                          setCopyMessage(null)
                        }}
                      />
                    </div>
                  </div>

                  <div>
                    <label htmlFor="boolean-query" className="mb-2 block text-sm font-medium text-slate-300">Editable Boolean query</label>
                    <textarea
                      id="boolean-query"
                      aria-label="Editable Boolean query"
                      className="textarea-shell min-h-32 font-mono text-sm"
                      value={query}
                      onChange={event => {
                        setQueryDraft({ source: generated, value: event.target.value })
                        setCopyMessage(null)
                      }}
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <button type="button" className="button-primary inline-flex items-center gap-2" disabled={!query.trim()} onClick={() => void handleCopy()}>
                      <Copy size={16} />
                      Copy Query
                    </button>
                    <button type="button" className="button-secondary inline-flex items-center gap-2" onClick={() => setQueryDraft(null)}>
                      <Wand2 size={16} />
                      Regenerate Query
                    </button>
                    <button type="button" className="button-secondary inline-flex items-center gap-2" onClick={resetFields}>
                      <RotateCcw size={16} />
                      Reset
                    </button>
                    {copyMessage && <p role="status" className="text-sm text-slate-300">{copyMessage}</p>}
                  </div>
                  {hasManualOverride && (
                    <p className="text-xs text-amber-300">
                      Manual edits are preserved until the query inputs change. Regenerate or reset to restore the generated version.
                    </p>
                  )}
                  <p className="text-xs text-slate-400">
                    This tool only builds query text. It does not search LinkedIn, contact job boards, or source candidate profiles.
                  </p>
                </>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}

function KeywordField({
  id,
  label,
  placeholder,
  value,
  onChange,
}: {
  id: string
  label: string
  placeholder: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-medium text-slate-300">{label}</label>
      <input
        id={id}
        className="input-shell h-11 py-2"
        value={value}
        placeholder={placeholder}
        onChange={event => onChange(event.target.value)}
      />
    </div>
  )
}
