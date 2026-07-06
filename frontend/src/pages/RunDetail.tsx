import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Approval, WorkflowRun } from '../api/types'
import { StatusChip } from '../components/flow/RunPanel'

function StepCard({
  step,
}: {
  step: NonNullable<WorkflowRun['steps']>[number]
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
      <div className="flex items-center gap-3">
        <span className="font-mono text-sm text-slate-200">{step.node_id}</span>
        <span className="text-xs text-slate-500">{step.node_type}</span>
        <span className="ml-auto">
          <StatusChip status={step.status} />
        </span>
      </div>
      {step.error && (
        <p className="mt-2 rounded-lg border border-red-900 bg-red-950/40 px-2 py-1 text-xs text-red-300">
          {step.error}
        </p>
      )}
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-slate-400">Input</summary>
        <pre className="mt-1 overflow-x-auto rounded-lg bg-slate-950 p-2 text-slate-300">
          {JSON.stringify(step.input, null, 2)}
        </pre>
      </details>
      <details className="mt-1 text-xs">
        <summary className="cursor-pointer text-slate-400">Output</summary>
        <pre className="mt-1 overflow-x-auto rounded-lg bg-slate-950 p-2 text-slate-300">
          {JSON.stringify(step.output, null, 2)}
        </pre>
      </details>
    </div>
  )
}

export function RunDetail() {
  const { id } = useParams()
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [approval, setApproval] = useState<Approval | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .get<WorkflowRun>(`/api/runs/${id}`)
      .then((r) => {
        setRun(r)
        if (r.status === 'waiting_approval') {
          api
            .get<Approval[]>('/api/approvals?status=pending')
            .then((list) =>
              setApproval(list.find((a) => a.run_id === r.id) ?? null),
            )
            .catch(() => setApproval(null))
        } else {
          setApproval(null)
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'load failed'))
  }, [id])

  useEffect(load, [load])

  const resolve = async (decision: 'approved' | 'rejected') => {
    if (!approval) return
    try {
      await api.post(`/api/approvals/${approval.id}/resolve`, { decision })
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'resolve failed')
    }
  }

  if (error) return <p className="text-sm text-red-300">{error}</p>
  if (!run) return <p className="text-sm text-slate-400">Loading…</p>

  return (
    <div data-testid="run-detail" className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold">Run #{run.id}</h1>
        <StatusChip status={run.status} />
        {run.dry_run && <span className="text-xs text-slate-400">dry run</span>}
        <Link
          to={`/automation/workflows/${run.workflow_id}`}
          className="ml-auto text-sm text-cyan-300 hover:underline"
        >
          Open workflow →
        </Link>
      </div>
      <p className="text-sm text-slate-400">
        {run.trigger_kind} · ${run.cost_usd.toFixed(4)} · {run.tokens_in}/
        {run.tokens_out} tokens
      </p>
      {run.error && (
        <p className="rounded-lg border border-red-900 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          {run.error}
        </p>
      )}
      {run.status === 'waiting_approval' && approval && (
        <div className="flex items-center gap-3 rounded-xl border border-orange-800 bg-orange-950/30 p-3">
          <span className="text-sm text-orange-200">{approval.message}</span>
          <button
            type="button"
            className="ml-auto rounded-lg bg-green-500 px-3 py-1 text-sm font-medium text-slate-950"
            onClick={() => void resolve('approved')}
          >
            Approve
          </button>
          <button
            type="button"
            className="rounded-lg bg-red-500 px-3 py-1 text-sm font-medium text-slate-950"
            onClick={() => void resolve('rejected')}
          >
            Reject
          </button>
        </div>
      )}
      <div className="space-y-2">
        {(run.steps ?? []).map((step) => (
          <StepCard key={step.id} step={step} />
        ))}
      </div>
    </div>
  )
}
