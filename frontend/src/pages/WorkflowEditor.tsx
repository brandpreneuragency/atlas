import { ReactFlowProvider } from '@xyflow/react'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type { Workflow } from '../api/types'
import { Canvas } from '../components/flow/Canvas'
import { NodePalette } from '../components/flow/NodePalette'
import { useGraph } from '../components/flow/useGraph'

function EditorInner({ workflow }: { workflow: Workflow }) {
  const graph = useGraph(workflow.graph)
  const [name, setName] = useState(workflow.name)
  const [version, setVersion] = useState(workflow.version)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const navigate = useNavigate()

  // unsaved-changes guard (browser navigation)
  useEffect(() => {
    if (!graph.dirty) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [graph.dirty])

  const save = useCallback(async () => {
    setError(null)
    try {
      const newVersion = await graph.save(workflow.id, {
        name,
        description: workflow.description,
        max_runs_per_hour: workflow.max_runs_per_hour,
        budget_usd_per_run: workflow.budget_usd_per_run,
      })
      setVersion(newVersion)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'save failed')
    }
  }, [graph, name, workflow])

  return (
    <div className="flex h-full flex-col gap-3" data-testid="workflow-editor">
      <div className="flex items-center gap-3">
        <button
          type="button"
          className="rounded-lg border border-slate-700 px-2 py-1 text-sm text-slate-300"
          onClick={() => {
            if (graph.dirty && !window.confirm('Discard unsaved changes?')) return
            navigate('/automation')
          }}
        >
          ← Back
        </button>
        <input
          aria-label="Workflow name"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-lg font-semibold"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <span className="text-sm text-slate-500" data-testid="workflow-version">
          v{version}
        </span>
        {graph.dirty && (
          <span className="text-xs text-amber-300" data-testid="dirty-indicator">
            unsaved changes
          </span>
        )}
        <button
          type="button"
          className="ml-auto rounded-lg bg-cyan-500 px-4 py-1.5 text-sm font-medium text-slate-950"
          onClick={() => void save()}
        >
          Save
        </button>
      </div>
      {error && (
        <p className="rounded-lg border border-red-800 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}
      <div className="flex min-h-0 flex-1 gap-3">
        <NodePalette />
        <Canvas
          nodes={graph.nodes}
          edges={graph.edges}
          setNodes={graph.setNodes}
          setEdges={graph.setEdges}
          onDropNode={graph.addNode}
          onSelectNode={setSelected}
          markDirty={graph.markDirty}
        />
        {selected && (
          <div data-testid="selected-node-id" className="hidden">
            {selected}
          </div>
        )}
      </div>
    </div>
  )
}

export function WorkflowEditor() {
  const { id } = useParams()
  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<Workflow>(`/api/workflows/${id}`)
      .then(setWorkflow)
      .catch((err) => setError(err instanceof Error ? err.message : 'load failed'))
  }, [id])

  if (error) return <p className="text-sm text-red-300">{error}</p>
  if (!workflow) return <p className="text-sm text-slate-400">Loading…</p>
  return (
    <ReactFlowProvider>
      <EditorInner workflow={workflow} />
    </ReactFlowProvider>
  )
}
