import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../features/auth/AuthContext'
import Brand from '../components/shared/Brand'

export default function LoginPage() {
  const { signIn, loading, error } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLocalError(null)
    if (!email || !password) {
      setLocalError('Email and password are required.')
      return
    }
    try {
      await signIn(email, password)
      navigate('/dashboard')
    } catch {
      // error set in context
    }
  }

  return (
    <div className="app-shell flex min-h-screen items-center justify-center p-4 sm:p-8">
      <div className="panel grid w-full max-w-5xl overflow-hidden lg:grid-cols-[1.1fr_0.9fr]">
        <div className="relative flex flex-col justify-between overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(99,102,241,0.25),_transparent_32%),linear-gradient(135deg,#0f172a,#111827_42%,#0b0f19)] p-8 lg:p-10">
          <div className="absolute inset-0 opacity-30" aria-hidden="true">
            <div className="absolute left-10 top-12 h-40 w-40 rounded-full bg-indigo-500/25 blur-3xl" />
            <div className="absolute bottom-10 right-10 h-52 w-52 rounded-full bg-cyan-500/20 blur-3xl" />
          </div>

          <div className="relative z-10">
            <Brand size="large" className="relative z-10 mb-8" />

            <div className="space-y-4">
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-300">Talent intelligence</p>
              <h1 className="max-w-md text-4xl font-semibold leading-tight text-white lg:text-5xl">
                Match great candidates to the right roles.
              </h1>
              <p className="max-w-md text-sm leading-7 text-slate-300">
                Screen faster, evaluate with AI insight, and keep every hiring decision grounded in relevant skills and role-fit signals.
              </p>
            </div>
          </div>

          <div className="relative z-10 mt-10 grid gap-3 sm:grid-cols-3">
            {[
              ['Role relevance', 'Compare profiles against job requirements'],
              ['Clear signals', 'Review skills and compatibility evidence'],
              ['Human review', 'Keep hiring decisions with your team'],
            ].map(([title, description]) => (
              <div key={title} className="rounded-2xl border border-slate-700/80 bg-slate-900/40 p-3 backdrop-blur-sm">
                <div className="text-sm font-semibold text-white">{title}</div>
                <div className="mt-1 text-[11px] leading-5 text-slate-400">{description}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-center bg-slate-950/70 p-6 lg:p-10">
          <form onSubmit={submit} className="w-full max-w-md space-y-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Welcome back</p>
              <h2 className="mt-3 text-3xl font-semibold text-white">Sign in</h2>
            </div>

            <div className="space-y-2">
              <label htmlFor="login-email" className="block text-sm font-medium text-slate-300">Email</label>
              <input
                id="login-email"
                className="input-shell"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="recruiter@apexrecruit.com"
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="login-password" className="block text-sm font-medium text-slate-300">Password</label>
              <div className="relative">
                <input
                  id="login-password"
                  className="input-shell pr-11"
                  type={show ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  onClick={() => setShow(s => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md border border-slate-700 bg-slate-900/80 p-1.5 text-slate-300 hover:border-slate-500 hover:text-white"
                  aria-label={show ? 'Hide password' : 'Show password'}
                >
                  {show ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {(localError || error) && (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
                {localError || error}
              </div>
            )}

            <button type="submit" disabled={loading} className="button-primary flex w-full items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-70">
              {loading ? 'Signing in...' : 'Sign in'}
              <ArrowRight size={18} />
            </button>
            <p className="text-center text-sm text-slate-400">
              New to Apex Recruit? <Link to="/register" className="font-medium text-indigo-200 hover:text-white hover:underline">Create an account</Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  )
}