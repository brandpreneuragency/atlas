import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { WorkflowRun } from '../api/types'

export function RunDetail() {
  const { id } = useParams()
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<WorkflowRun>(`/api/runs/${id}`)
      .then(setRun)
      .catch((err) => setError(err instanceof Error ? err.message : 'load failed'))
  }, [id])

  if (error) return <p className="text-sm text-red-300">{error}</p>
  if (!run) return <p className="text-sm text-slate-400">Loading…</p>
  return (
    <div data-testid="run-detail">
      <h1 className="text-2xl font-semibold">Run #{run.id}</h1>
      <p className="mt-1 text-sm text-slate-400">{run.status}</p>
    </div>
  )
}
