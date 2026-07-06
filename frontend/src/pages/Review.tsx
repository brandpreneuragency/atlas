import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../api/client'

type ReviewItem = {
  name: string
  frontmatter: Record<string, unknown>
  body_preview: string
  source_path: string | null
}

export function Review() {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [processing, setProcessing] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const refetch = useCallback(async () => {
    try {
      const rows = await api.get<ReviewItem[]>('/api/review')
      setItems(rows)
      setProcessing((current) => {
        const names = new Set(rows.map((r) => r.name))
        const next: Record<string, string> = {}
        for (const [name, runId] of Object.entries(current)) {
          if (names.has(name)) next[name] = runId // still pending → keep spinner
        }
        return next
      })
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    void refetch()
  }, [refetch])

  useEffect(() => {
    // poll faster while a Hermes run is processing a note
    if (Object.keys(processing).length === 0) {
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = null
      return
    }
    if (!pollRef.current) {
      pollRef.current = setInterval(() => void refetch(), 3_000)
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [processing, refetch])

  const decide = async (name: string, decision: 'approved' | 'rejected') => {
    setProcessing((current) => ({ ...current, [name]: 'starting' }))
    try {
      const result = await api.post<{ run_id: string }>(
        `/api/review/${encodeURIComponent(name)}/decide`,
        { decision },
      )
      setProcessing((current) => ({ ...current, [name]: result.run_id }))
      await refetch()
    } catch (e) {
      setError((e as Error).message)
      setProcessing((current) => {
        const next = { ...current }
        delete next[name]
        return next
      })
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-semibold">Review queue</h1>
      <p className="mt-2 text-slate-400">
        Brain review notes pending a decision — approve dispatches the Hermes brain workflow
      </p>
      {error && <p className="mt-4 text-sm text-rose-400">{error}</p>}
      {items.length === 0 ? (
        <p className="mt-8 text-slate-500">Nothing waiting for review.</p>
      ) : (
        <ul className="mt-6 space-y-4">
          {items.map((item) => {
            const busy = item.name in processing
            return (
              <li
                key={item.name}
                data-testid={`review-${item.name}`}
                className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-100">{item.name}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {Object.entries(item.frontmatter).map(([key, value]) => (
                        <span
                          key={key}
                          className="rounded-full bg-slate-800 px-2.5 py-0.5 text-xs text-slate-300"
                        >
                          {key}: {String(value)}
                        </span>
                      ))}
                    </div>
                    <p className="mt-3 whitespace-pre-wrap text-sm text-slate-400">
                      {item.body_preview}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {busy ? (
                      <span className="animate-pulse rounded-xl bg-cyan-400/10 px-4 py-2 text-sm text-cyan-300">
                        Hermes working…
                      </span>
                    ) : (
                      <>
                        <button
                          onClick={() => void decide(item.name, 'approved')}
                          className="rounded-xl bg-emerald-500/15 px-4 py-2 text-sm text-emerald-300 hover:bg-emerald-500/25"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => void decide(item.name, 'rejected')}
                          className="rounded-xl bg-rose-500/15 px-4 py-2 text-sm text-rose-300 hover:bg-rose-500/25"
                        >
                          Reject
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
