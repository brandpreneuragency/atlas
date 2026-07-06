import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../../api/client'
import type { WorkflowRun } from '../../api/types'

const STATUS_COLORS: Record<string, string> = {
  succeeded: 'bg-green-500/20 text-green-300',
  failed: 'bg-red-500/20 text-red-300',
  running: 'bg-blue-500/20 text-blue-300',
  queued: 'bg-slate-500/20 text-slate-300',
  waiting_approval: 'bg-orange-500/20 text-orange-300',
  cancelled: 'bg-slate-500/20 text-slate-400',
  budget_exceeded: 'bg-amber-500/20 text-amber-300',
}

export function StatusChip({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status] ?? 'bg-slate-500/20 text-slate-300'}`}
    >
      {status}
    </span>
  )
}

function duration(run: WorkflowRun): string {
  if (!run.started_at || !run.finished_at) return '—'
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
  return `${(ms / 1000).toFixed(1)}s`
}

export function RunPanel({
  workflowId,
  refreshKey = 0,
  onRunStarted,
}: {
  workflowId: number
  refreshKey?: number
  onRunStarted?: (runId: number) => void
}) {
  const [runs, setRuns] = useState<WorkflowRun[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .get<WorkflowRun[]>(`/api/runs?workflow_id=${workflowId}&limit=20`)
      .then(setRuns)
      .catch((err) => setError(err instanceof Error ? err.message : 'load failed'))
  }, [workflowId])

  useEffect(load, [load, refreshKey])

  const start = async (dryRun: boolean) => {
    setError(null)
    try {
      const res = await api.post<{ run_id: number }>(
        `/api/workflows/${workflowId}/run`,
        { dry_run: dryRun },
      )
      onRunStarted?.(res.run_id)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'run failed')
    }
  }

  return (
    <div
      data-testid="run-panel"
      className="w-72 shrink-0 space-y-3 overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-4"
    >
      <div className="flex gap-2">
        <button
          type="button"
          className="flex-1 rounded-lg bg-green-500 px-3 py-1.5 text-sm font-medium text-slate-950"
          onClick={() => void start(false)}
        >
          Run
        </button>
        <button
          type="button"
          className="flex-1 rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-200"
          onClick={() => void start(true)}
        >
          Dry run
        </button>
      </div>
      {error && <p className="text-xs text-red-300">{error}</p>}
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
        Recent runs
      </h3>
      <ul className="space-y-2">
        {runs.map((run) => (
          <li key={run.id} className="rounded-lg border border-slate-800 p-2 text-sm">
            <div className="flex items-center justify-between">
              <Link
                to={`/automation/runs/${run.id}`}
                className="font-medium text-cyan-300 hover:underline"
              >
                #{run.id}
              </Link>
              <StatusChip status={run.status} />
            </div>
            <div className="mt-1 flex justify-between text-xs text-slate-400">
              <span>
                {run.trigger_kind}
                {run.dry_run ? ' (dry)' : ''}
              </span>
              <span>
                {duration(run)} · ${run.cost_usd.toFixed(4)}
              </span>
            </div>
          </li>
        ))}
        {runs.length === 0 && (
          <li className="text-xs text-slate-500">No runs yet.</li>
        )}
      </ul>
    </div>
  )
}
