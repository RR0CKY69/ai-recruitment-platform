import type { ReactNode } from 'react'
import { LoaderCircle } from 'lucide-react'

interface PageHeaderProps {
  title: string
  eyebrow?: string
  description?: string
  actions?: ReactNode
}

export function PageHeader({ title, eyebrow, description, actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1 text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">{eyebrow}</p>}
        <h1 className="page-title">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">{description}</p>}
      </div>
      {actions && <div className="w-full shrink-0 sm:w-auto">{actions}</div>}
    </header>
  )
}

type StatusTone = 'success' | 'warning' | 'neutral' | 'error' | 'info'

interface StatusBadgeProps {
  label: string
  tone?: StatusTone
}

export function StatusBadge({ label, tone = 'neutral' }: StatusBadgeProps) {
  return <span className={`status-pill ${tone}`}>{label}</span>
}

interface ScoreDisplayProps {
  score: number | null
  max?: number
  label?: string
}

export function ScoreDisplay({ score, max = 100, label }: ScoreDisplayProps) {
  const percent = score === null || !Number.isFinite(score) || max <= 0
    ? null
    : Math.round((score / max) * 100)

  return (
    <span
      className="font-semibold tabular-nums text-slate-100"
      aria-label={percent === null ? `${label ? `${label} ` : ''}Score unavailable` : `${label ? `${label} ` : ''}${percent}%`}
    >
      {label && `${label} `}
      {percent === null ? '—' : `${percent}%`}
    </span>
  )
}

interface SkillChipsProps {
  skills: string[]
  label?: string
}

export function SkillChips({ skills, label = 'Skills' }: SkillChipsProps) {
  if (skills.length === 0) return <p className="text-sm text-slate-400">No {label.toLowerCase()} listed.</p>

  return (
    <ul aria-label={label} className="flex flex-wrap gap-2">
      {skills.map(skill => (
        <li key={skill} className="rounded-full border border-indigo-400/30 bg-indigo-400/10 px-2.5 py-1 text-xs text-indigo-100">
          {skill}
        </li>
      ))}
    </ul>
  )
}

export function LoadingState({ label = 'Loading...' }: { label?: string }) {
  return (
    <p role="status" className="inline-flex items-center gap-2 text-sm text-slate-300">
      <LoaderCircle size={16} aria-hidden="true" className="animate-spin" />
      {label}
    </p>
  )
}

interface EmptyStateProps {
  title: string
  description?: string
  action?: ReactNode
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <section className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/30 px-5 py-8 text-center">
      <h2 className="font-semibold text-slate-100">{title}</h2>
      {description && <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-400">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </section>
  )
}

interface ErrorStateProps {
  title: string
  description?: string
}

export function ErrorState({ title, description }: ErrorStateProps) {
  return (
    <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
      <p className="font-medium">{title}</p>
      {description && <p className="mt-1 text-red-200/80">{description}</p>}
    </div>
  )
}

interface FormFieldProps {
  id: string
  label: string
  required?: boolean
  hint?: string
  error?: string
  children: ReactNode
}

export function FormField({ id, label, required = false, hint, error, children }: FormFieldProps) {
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined

  return (
    <div className="space-y-2">
      <label
        htmlFor={id}
        className={`block text-sm font-medium text-slate-300 ${required ? "after:ml-1 after:text-indigo-300 after:content-['*']" : ''}`}
      >
        {label}
      </label>
      {children}
      {hint && <p id={hintId} className="text-xs leading-5 text-slate-400">{hint}</p>}
      {error && <p id={errorId} className="text-xs text-red-300">{error}</p>}
    </div>
  )
}
