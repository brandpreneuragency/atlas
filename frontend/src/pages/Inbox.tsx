import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { Approval } from '../api/types'
import { DataState } from '../components/ui/DataState'

function relativeTime(ts: string): string {
  const then = new Date(ts).getTime()
  const diff = Math.max(0, Date.now() - then)
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export function Inbox() {
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(() => {
    api
      .get<Approval[]>('/api/approvals?status=pending')
      .then((rows) => {
        setApprovals(rows)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    refetch()
    const timer = setInterval(refetch, 30_000)
    return () => clearInterval(timer)
  }, [refetch])

  const resolve = (id: number, decision: 'approved' | 'rejected') => {
    // optimistic removal — restored by the next poll if the call failed
    setApprovals((current) => current.filter((a) => a.id !== id))
    api.post(`/api/approvals/${id}/resolve`, { decision }).catch((e: Error) => {
      setError(e.message)
      refetch()
    })
  }

  return (
    <div>
      <h1 className="text-3xl font-semibold">Inbox</h1>
      <p className="mt-2 text-slate-400">Pending approvals across workflows and Hermes runs</p>
      <DataState
        loading={loading}
        error={error}
        empty="No pending approvals."
        isEmpty={approvals.length === 0}
        onRetry={() => {
          setLoading(true)
          refetch()
        }}
      >
        <ul className="mt-6 space-y-3">
          {approvals.map((approval) => (
            <li
              key={approval.id}
              data-testid={`approval-${approval.id}`}
              className="flex items-center gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm text-slate-100">{approval.message}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {approval.kind === 'hermes_run' ? 'Hermes run approval' : 'Workflow gate'} ·{' '}
                  {approval.run_id !== null && (
                    <>
                      <Link
                        to={`/automation/runs/${approval.run_id}`}
                        className="text-cyan-300 hover:underline"
                      >
                        run #{approval.run_id}
                      </Link>{' '}
                      ·{' '}
                    </>
                  )}
                  {relativeTime(approval.requested_at)}
                </p>
              </div>
              <button
                onClick={() => resolve(approval.id, 'approved')}
                className="rounded-xl bg-emerald-500/15 px-4 py-2 text-sm text-emerald-300 hover:bg-emerald-500/25"
              >
                Approve
              </button>
              <button
                onClick={() => resolve(approval.id, 'rejected')}
                className="rounded-xl bg-rose-500/15 px-4 py-2 text-sm text-rose-300 hover:bg-rose-500/25"
              >
                Reject
              </button>
            </li>
          ))}
        </ul>
      </DataState>
    </div>
  )
}
