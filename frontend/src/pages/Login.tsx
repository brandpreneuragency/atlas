import type { FormEvent } from 'react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import { useSession } from '../stores/useSession'

export function Login() {
  const navigate = useNavigate()
  const setAuthenticated = useSession((state) => state.setAuthenticated)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.post('/api/auth/login', { password })
      setAuthenticated(true)
      navigate('/')
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 text-slate-100">
      <form onSubmit={onSubmit} className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
        <p className="text-xs uppercase tracking-[0.35em] text-cyan-300">ATLAS Control</p>
        <h1 className="mt-3 text-2xl font-semibold">Sign in</h1>
        <label className="mt-6 block text-sm text-slate-300" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-cyan-400 focus:ring-2"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
        />
        {error ? <p className="mt-3 text-sm text-red-300">{error}</p> : null}
        <button
          className="mt-6 w-full rounded-xl bg-cyan-400 px-4 py-2 font-semibold text-slate-950 disabled:opacity-60"
          disabled={submitting}
          type="submit"
        >
          Sign in
        </button>
      </form>
    </main>
  )
}
