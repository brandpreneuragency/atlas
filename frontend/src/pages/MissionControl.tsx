import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import type { AgentStatus, AtlasEvent, HealthResponse } from '../api/types'
import { AgentCard } from '../components/cards/AgentCard'
import { Feed } from '../components/feed/Feed'
import { Card } from '../components/ui/Card'

function eventsToday(events: AtlasEvent[]): number {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const cutoff = start.getTime()
  return events.filter((e) => new Date(e.ts).getTime() >= cutoff).length
}

export function MissionControl({ initialFeed = [] }: { initialFeed?: AtlasEvent[] }) {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<HealthResponse>('/api/health'),
  })
  const agents = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.get<AgentStatus[]>('/api/agents'),
  })

  const todayCount = eventsToday(initialFeed)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Mission Control</h1>
        <p className="mt-2 text-slate-400">Live health and launchpad for ATLAS.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <AgentCardInline agent={agents.data?.[0] ?? null} isLoading={agents.isLoading} />
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-black/20">
          <h2 className="text-sm uppercase tracking-wider text-slate-500">Events today</h2>
          <p className="mt-2 text-3xl font-semibold text-emerald-300">{todayCount}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-black/20">
          <h2 className="text-sm uppercase tracking-wider text-slate-500">Runs today</h2>
          <p className="mt-2 text-3xl font-semibold text-slate-300">0</p>
        </div>
      </div>

      <Card title="System health">
        {health.isLoading ? <p className="text-slate-400">Loading…</p> : null}
        {health.error ? <p className="text-red-300">Health check failed</p> : null}
        {health.data ? (
          <dl className="grid gap-3 text-sm text-slate-300 sm:grid-cols-3">
            <div>
              <dt className="text-slate-500">Backend</dt>
              <dd className="font-medium text-emerald-300">{health.data.status}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Database</dt>
              <dd className="font-medium text-emerald-300">{health.data.db}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Hermes runs API</dt>
              <dd className="font-medium text-emerald-300">{health.data.hermes.runs_api}</dd>
            </div>
          </dl>
        ) : null}
      </Card>

      <Feed initialEvents={initialFeed} />
    </div>
  )
}

function AgentCardInline({
  agent,
  isLoading,
}: {
  agent: AgentStatus | null
  isLoading: boolean
}) {
  if (isLoading || !agent) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 text-slate-400">
        Loading agent…
      </div>
    )
  }
  return <AgentCard agent={agent} />
}