import { describeCron } from '../../lib/cron'

export type CronJob = {
  id: string
  name: string
  prompt?: string
  schedule?: { kind?: string; expr?: string; display?: string }
  enabled?: boolean
  state?: string
  last_status?: string
  last_error?: string | null
  next_run_at?: string | null
  skills?: string[]
}

const STATE_BADGE: Record<string, string> = {
  running: 'bg-emerald-400/15 text-emerald-200',
  scheduled: 'bg-cyan-400/15 text-cyan-200',
  paused: 'bg-slate-600/30 text-slate-300',
  error: 'bg-red-400/15 text-red-200',
}

export function CronJobRow({
  job,
  onAction,
  onEdit,
  onDelete,
}: {
  job: CronJob
  onAction: (id: string, action: 'pause' | 'resume' | 'trigger') => void
  onEdit: (job: CronJob) => void
  onDelete: (job: CronJob) => void
}) {
  const expr = job.schedule?.expr ?? ''
  const state = job.state ?? (job.enabled ? 'scheduled' : 'paused')
  return (
    <tr className="border-t border-slate-800/60">
      <td className="px-4 py-3 font-medium text-slate-100">{job.name}</td>
      <td className="px-4 py-3 text-slate-300">
        <span title={expr}>{describeCron(expr)}</span>
      </td>
      <td className="px-4 py-3">
        <span
          data-testid={`job-state-${job.id}`}
          title={job.last_error ?? undefined}
          className={`rounded-full px-2 py-0.5 text-xs ${
            STATE_BADGE[state] ?? 'bg-slate-700/40 text-slate-300'
          }`}
        >
          {state}
        </span>
      </td>
      <td className="px-4 py-3 text-slate-400">
        {job.next_run_at ? new Date(job.next_run_at).toLocaleString() : '—'}
      </td>
      <td className="px-4 py-3">
        <div className="flex justify-end gap-1.5">
          {job.enabled ? (
            <button
              type="button"
              className="rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
              onClick={() => onAction(job.id, 'pause')}
            >
              Pause
            </button>
          ) : (
            <button
              type="button"
              className="rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
              onClick={() => onAction(job.id, 'resume')}
            >
              Resume
            </button>
          )}
          <button
            type="button"
            className="rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
            onClick={() => onAction(job.id, 'trigger')}
          >
            Run now
          </button>
          <button
            type="button"
            className="rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
            onClick={() => onEdit(job)}
          >
            Edit
          </button>
          <button
            type="button"
            className="rounded-lg border border-red-900 px-2 py-1 text-xs text-red-300 hover:bg-red-950"
            onClick={() => onDelete(job)}
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  )
}
