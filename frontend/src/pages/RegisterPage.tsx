import axios from 'axios'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Eye, EyeOff } from 'lucide-react'
import Brand from '../components/shared/Brand'
import { FormField, PageHeader } from '../components/shared/Primitives'
import { registerUser } from '../features/auth/api'
import { apiClient } from '../services/apiClient'

interface RegistrationValues {
  fullName: string
  email: string
  password: string
  confirmPassword: string
  workspaceName: string
}

type RegistrationField = keyof RegistrationValues
type RegistrationErrors = Partial<Record<RegistrationField, string>>

const initialValues: RegistrationValues = {
  fullName: '',
  email: '',
  password: '',
  confirmPassword: '',
  workspaceName: '',
}

function getRegistrationError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 404) {
      return 'Registration is not available yet because the API endpoint is not implemented. No account was created. Please contact your administrator.'
    }
    const detail: unknown = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (error.response) return `Registration failed (HTTP ${error.response.status}). No account was created.`
    return `Unable to reach the registration API at ${apiClient.defaults.baseURL}. No account was created. Check your connection and try again.`
  }
  return 'Registration could not be completed. No account was created. Please try again.'
}

function validate(values: RegistrationValues): RegistrationErrors {
  const errors: RegistrationErrors = {}
  if (!values.fullName.trim()) errors.fullName = 'Enter your full name.'
  if (!values.email.trim()) {
    errors.email = 'Enter your email address.'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) {
    errors.email = 'Enter a valid email address.'
  }
  if (!values.password) {
    errors.password = 'Create a password.'
  } else if (values.password.length < 8) {
    errors.password = 'Use at least 8 characters.'
  }
  if (!values.confirmPassword) {
    errors.confirmPassword = 'Confirm your password.'
  } else if (values.confirmPassword !== values.password) {
    errors.confirmPassword = 'Passwords do not match.'
  }
  if (!values.workspaceName.trim()) errors.workspaceName = 'Enter your workspace or company name.'
  return errors
}

export default function RegisterPage() {
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState<RegistrationErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isComplete, setIsComplete] = useState(false)
  const [showPasswords, setShowPasswords] = useState(false)

  const updateValue = (field: RegistrationField, value: string) => {
    setValues(current => ({ ...current, [field]: value }))
    setErrors(current => ({
      ...current,
      [field]: undefined,
      ...(field === 'password' ? { confirmPassword: undefined } : {}),
    }))
    setApiError(null)
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setApiError(null)
    const nextErrors = validate(values)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return

    setIsSubmitting(true)
    try {
      await registerUser({
        full_name: values.fullName.trim(),
        email: values.email.trim(),
        password: values.password,
        workspace_name: values.workspaceName.trim(),
      })
      setIsComplete(true)
    } catch (error: unknown) {
      setApiError(getRegistrationError(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="app-shell flex min-h-screen items-center justify-center p-4 sm:p-8">
      <div className="panel grid w-full max-w-5xl overflow-hidden lg:grid-cols-[1.05fr_0.95fr]">
        <aside className="relative hidden flex-col justify-between overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(99,102,241,0.25),_transparent_32%),linear-gradient(135deg,#0f172a,#111827_42%,#0b0f19)] p-8 lg:flex lg:p-10">
          <div className="absolute inset-0 opacity-30" aria-hidden="true">
            <div className="absolute left-10 top-12 h-40 w-40 rounded-full bg-indigo-500/25 blur-3xl" />
            <div className="absolute bottom-10 right-10 h-52 w-52 rounded-full bg-cyan-500/20 blur-3xl" />
          </div>
          <div className="relative z-10">
            <Brand size="large" className="mb-12" />
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-300">Talent intelligence</p>
            <h1 className="mt-4 max-w-md text-4xl font-semibold leading-tight text-white">
              Build a more thoughtful hiring workflow.
            </h1>
            <p className="mt-4 max-w-md text-sm leading-7 text-slate-300">
              Bring your team, roles, and candidate evaluations together in one considered workspace.
            </p>
          </div>
          <p className="relative z-10 text-xs leading-5 text-slate-400">
            Hiring decisions stay with your team. Apex Recruit provides workflow and decision-support tools.
          </p>
        </aside>

        <main className="flex items-center justify-center bg-slate-950/70 p-6 sm:p-8 lg:p-10">
          <div className="w-full max-w-md">
            <Brand size="large" className="mb-7 lg:hidden" />
            <PageHeader
              eyebrow="Get started"
              title="Create your account"
              description="Set up your recruiter profile and workspace."
            />

            {isComplete ? (
              <div role="status" className="space-y-4 rounded-2xl border border-emerald-500/25 bg-emerald-500/10 p-4">
                <p className="text-sm leading-6 text-emerald-100">Your registration request was completed. Sign in to continue.</p>
                <Link to="/login" className="button-primary inline-flex items-center gap-2">
                  Go to sign in <ArrowRight size={17} aria-hidden="true" />
                </Link>
              </div>
            ) : (
              <form noValidate onSubmit={submit} className="space-y-4">
                <FormField id="full-name" label="Full name" required error={errors.fullName}>
                  <input
                    id="full-name"
                    className="input-shell"
                    autoComplete="name"
                    required
                    aria-invalid={Boolean(errors.fullName)}
                    aria-describedby={errors.fullName ? 'full-name-error' : undefined}
                    value={values.fullName}
                    onChange={event => updateValue('fullName', event.target.value)}
                    placeholder="Jordan Lee"
                  />
                </FormField>

                <FormField id="register-email" label="Email" required error={errors.email}>
                  <input
                    id="register-email"
                    className="input-shell"
                    type="email"
                    autoComplete="email"
                    required
                    aria-invalid={Boolean(errors.email)}
                    aria-describedby={errors.email ? 'register-email-error' : undefined}
                    value={values.email}
                    onChange={event => updateValue('email', event.target.value)}
                    placeholder="you@company.com"
                  />
                </FormField>

                <FormField
                  id="register-password"
                  label="Password"
                  required
                  hint="Use at least 8 characters and choose a unique password."
                  error={errors.password}
                >
                  <div className="relative">
                    <input
                      id="register-password"
                      className="input-shell pr-12"
                      type={showPasswords ? 'text' : 'password'}
                      autoComplete="new-password"
                      minLength={8}
                      required
                      aria-invalid={Boolean(errors.password)}
                      aria-describedby={`register-password-hint${errors.password ? ' register-password-error' : ''}`}
                      value={values.password}
                      onChange={event => updateValue('password', event.target.value)}
                      placeholder="Create a password"
                    />
                    <button
                      type="button"
                      aria-label={showPasswords ? 'Hide passwords' : 'Show passwords'}
                      aria-pressed={showPasswords}
                      onClick={() => setShowPasswords(current => !current)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-2 text-slate-400 transition hover:bg-slate-800 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400"
                    >
                      {showPasswords ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
                    </button>
                  </div>
                </FormField>

                <FormField id="confirm-password" label="Confirm password" required error={errors.confirmPassword}>
                  <input
                    id="confirm-password"
                    className="input-shell"
                    type={showPasswords ? 'text' : 'password'}
                    autoComplete="new-password"
                    required
                    aria-invalid={Boolean(errors.confirmPassword)}
                    aria-describedby={errors.confirmPassword ? 'confirm-password-error' : undefined}
                    value={values.confirmPassword}
                    onChange={event => updateValue('confirmPassword', event.target.value)}
                    placeholder="Enter your password again"
                  />
                </FormField>

                <FormField id="workspace-name" label="Workspace or company name" required error={errors.workspaceName}>
                  <input
                    id="workspace-name"
                    className="input-shell"
                    autoComplete="organization"
                    required
                    aria-invalid={Boolean(errors.workspaceName)}
                    aria-describedby={errors.workspaceName ? 'workspace-name-error' : undefined}
                    value={values.workspaceName}
                    onChange={event => updateValue('workspaceName', event.target.value)}
                    placeholder="Acme Talent"
                  />
                </FormField>

                {apiError && <p role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm leading-6 text-red-200">{apiError}</p>}

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="button-primary flex w-full items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {isSubmitting ? 'Creating account...' : 'Create account'}
                  {!isSubmitting && <ArrowRight size={18} aria-hidden="true" />}
                </button>
                <p className="text-center text-sm text-slate-400">
                  Already have an account? <Link to="/login" className="font-medium text-indigo-200 hover:text-white hover:underline">Sign in</Link>
                </p>
              </form>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
