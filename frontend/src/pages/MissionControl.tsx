import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import type { HealthResponse } from '../api/types'
import { Card } from '../components/ui/Card'

export function MissionControl() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<HealthResponse>('/api/health'),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Mission Control</h1>
        <p className="mt-2 text-slate-400">Live health and launchpad for ATLAS.</p>
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
    </div>
  )
}
