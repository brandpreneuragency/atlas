import { useEffect, useState } from 'react'

import { api } from '../api/client'

export function Settings() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [paused, setPaused] = useState<boolean | null>(null)

  useEffect(() => {
    api
      .get<{ paused: boolean }>('/api/killswitch')
      .then((body) => setPaused(body.paused))
      .catch(() => setPaused(null))
  }, [])

  const changePassword = async () => {
    setMessage(null)
    try {
      await api.post('/api/settings/password', { current, new: next })
      setMessage('Password changed.')
      setCurrent('')
      setNext('')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'change failed')
    }
  }

  return (
    <div className="max-w-xl space-y-8" data-testid="settings-page">
      <h1 className="text-3xl font-semibold">Settings</h1>

      <section className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
        <h2 className="text-lg font-medium text-slate-200">Change password</h2>
        <label className="block text-sm text-slate-300">
          Current password
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </label>
        <label className="block text-sm text-slate-300">
          New password
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </label>
        {message && <p className="text-sm text-slate-300">{message}</p>}
        <button
          type="button"
          disabled={!current || !next}
          className="rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950 disabled:opacity-40"
          onClick={() => void changePassword()}
        >
          Change password
        </button>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
        <h2 className="text-lg font-medium text-slate-200">Kill switch</h2>
        <p className="mt-2 text-sm text-slate-400">
          {paused === null
            ? 'state unknown'
            : paused
              ? 'ENGAGED — automation paused'
              : 'released — automation running'}
        </p>
      </section>

      <section className="rounded-2xl border border-dashed border-slate-800 p-5 text-sm text-slate-500">
        Notifications — coming in Phase 7
      </section>
      <section className="rounded-2xl border border-dashed border-slate-800 p-5 text-sm text-slate-500">
        Backups — coming in Phase 8
      </section>
    </div>
  )
}
