import type { AgentStatus } from '../../api/types'

export function AgentCard({ agent }: { agent: AgentStatus }) {
  const ok = agent.status === 'ok'
  return (
    <article
      data-testid="agent-card"
      className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-black/20"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-100">{agent.name}</h3>
        <span
          aria-label={`status-${agent.status}`}
          className={`h-3 w-3 rounded-full ${
            ok ? 'bg-emerald-400' : 'bg-red-500'
          }`}
        />
      </div>
      <dl className="mt-4 grid gap-2 text-sm text-slate-300">
        <div className="flex justify-between">
          <dt className="text-slate-500">Status</dt>
          <dd data-testid="agent-status">{agent.status}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Model</dt>
          <dd data-testid="agent-model">{agent.model ?? '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Active runs</dt>
          <dd data-testid="agent-runs">{agent.active_runs}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Kind</dt>
          <dd>{agent.kind}</dd>
        </div>
      </dl>
    </article>
  )
}