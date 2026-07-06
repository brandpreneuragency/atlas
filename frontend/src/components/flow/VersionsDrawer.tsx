import { useEffect, useState } from 'react'

import { api } from '../../api/client'
import type { Workflow, WorkflowVersion } from '../../api/types'

type VersionsDrawerProps = {
  workflowId: number
  currentVersion: number
  onRollback: (workflow: Workflow) => void
  onClose: () => void
}

export function VersionsDrawer({
  workflowId,
  currentVersion,
  onRollback,
  onClose,
}: VersionsDrawerProps) {
  const [versions, setVersions] = useState<WorkflowVersion[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<WorkflowVersion[]>(`/api/workflows/${workflowId}/versions`)
      .then((list) => setVersions([...list].reverse()))
      .catch((err) => setError(err instanceof Error ? err.message : 'load failed'))
  }, [workflowId])

  const rollback = async (version: number) => {
    if (!window.confirm(`Rollback to v${version}? This creates a new version.`)) return
    try {
      const workflow = await api.post<Workflow>(
        `/api/workflows/${workflowId}/rollback`,
        { version },
      )
      onRollback(workflow)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'rollback failed')
    }
  }

  return (
    <aside
      data-testid="versions-drawer"
      className="w-72 shrink-0 space-y-2 overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-4"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200">Versions</h3>
        <button type="button" aria-label="Close versions" className="text-slate-400" onClick={onClose}>
          ✕
        </button>
      </div>
      {error && <p className="text-xs text-red-300">{error}</p>}
      <ul className="space-y-2">
        {versions.map((v) => (
          <li
            key={v.id}
            className="flex items-center gap-2 rounded-lg border border-slate-800 px-3 py-2 text-sm"
          >
            <span className="font-mono text-slate-200">v{v.version}</span>
            <span className="text-xs text-slate-500">
              {new Date(v.created_at).toLocaleString()}
            </span>
            {v.version === currentVersion ? (
              <span className="ml-auto text-xs text-cyan-300">current</span>
            ) : (
              <button
                type="button"
                className="ml-auto rounded border border-slate-600 px-2 py-0.5 text-xs text-slate-300"
                onClick={() => void rollback(v.version)}
              >
                Rollback
              </button>
            )}
          </li>
        ))}
      </ul>
    </aside>
  )
}
