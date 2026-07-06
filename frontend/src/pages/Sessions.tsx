import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { HermesSession } from '../api/types'

const SOURCE_BADGE: Record<string, string> = {
  cron: 'bg-amber-400/15 text-amber-200',
  chat: 'bg-cyan-400/15 text-cyan-200',
  api: 'bg-violet-400/15 text-violet-200',
}

export function Sessions() {
  const [sessions, setSessions] = useState<HermesSession[]>([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    const suffix = params.toString() ? `?${params.toString()}` : ''
    api
      .get<HermesSession[]>(`/api/hermes/sessions${suffix}`)
      .then((rows) => {
        if (!cancelled) setSessions(rows)
      })
      .catch(() => {
        if (!cancelled) setSessions([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [q])

  return (
    <div className="space-y-6" data-testid="sessions-page">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold">Sessions</h1>
        <input
          aria-label="search sessions"
          className="w-72 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="search…"
        />
      </div>
      <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-900 text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-2">ID</th>
              <th className="px-4 py-2">Title</th>
              <th className="px-4 py-2">Updated</th>
              <th className="px-4 py-2">Source</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-slate-400">
                  Loading…
                </td>
              </tr>
            ) : sessions.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-slate-400">
                  No sessions.
                </td>
              </tr>
            ) : (
              sessions.map((s) => (
                <tr key={s.id} className="border-t border-slate-800/60">
                  <td className="px-4 py-2">
                    <Link className="text-cyan-200 hover:underline" to={`/sessions/${s.id}`}>
                      {s.id}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-slate-200">{s.title ?? '—'}</td>
                  <td className="px-4 py-2 text-slate-400">
                    {s.updated_at ? new Date(s.updated_at * 1000).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-2">
                    {s.source ? (
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs ${
                          SOURCE_BADGE[s.source] ?? 'bg-slate-700/40 text-slate-300'
                        }`}
                      >
                        {s.source}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  )
}