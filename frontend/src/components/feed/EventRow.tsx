import type { AtlasEvent, EventKind } from '../../api/types'

const KIND_ICONS: Record<string, string> = {
  'run.started': '▶',
  'run.step_started': '↳',
  'run.step_finished': '✓',
  'run.waiting_approval': '⏸',
  'run.finished': '✓',
  'run.failed': '✕',
  'hermes.run_event': '🛰',
  'hermes.cron_changed': '⏰',
  'hermes.error': '⚠',
  'file.changed': '📝',
  'file.created': '📄',
  'file.deleted': '🗑',
  'approval.requested': '❓',
  'approval.resolved': '✔',
  'review.decided': '📚',
  'system.killswitch': '🛑',
  'system.login': '🔑',
  'system.error': '⚠',
}

function relativeTime(ts: string): string {
  const then = new Date(ts).getTime()
  const diff = Math.max(0, Date.now() - then)
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

export function EventRow({ event }: { event: AtlasEvent }) {
  const icon = KIND_ICONS[event.kind as EventKind] ?? '•'
  return (
    <li className="flex items-start gap-3 border-b border-slate-800/60 py-2.5 last:border-b-0">
      <span aria-label={`kind-${event.kind}`} className="mt-0.5 w-5 text-center">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-slate-200">{event.payload.summary}</p>
        <p className="text-xs text-slate-500">
          <span data-testid="event-kind">{event.kind}</span> · {event.source} ·{' '}
          <span data-testid={`event-reltime-${event.id}`}>{relativeTime(event.ts)}</span>
        </p>
      </div>
    </li>
  )
}