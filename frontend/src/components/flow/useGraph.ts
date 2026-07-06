import type { Edge, Node } from '@xyflow/react'
import { useCallback, useState } from 'react'

import { api } from '../../api/client'
import type { Workflow, WorkflowGraph } from '../../api/types'

export type AtlasNodeData = {
  nodeType: string
  config: Record<string, unknown>
  [key: string]: unknown
}

export type AtlasNode = Node<AtlasNodeData, 'atlas'>

/** Backend graph JSON → React Flow state. Positions are persisted (§6). */
export function toFlow(graph: WorkflowGraph): { nodes: AtlasNode[]; edges: Edge[] } {
  return {
    nodes: graph.nodes.map((n) => ({
      id: n.id,
      type: 'atlas' as const,
      position: { x: n.position.x, y: n.position.y },
      data: { nodeType: n.type, config: n.config },
    })),
    edges: graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.condition ?? undefined,
      data: { condition: e.condition },
    })),
  }
}

/** React Flow state → backend graph JSON (lossless round-trip). */
export function fromFlow(nodes: AtlasNode[], edges: Edge[]): WorkflowGraph {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.data.nodeType,
      position: { x: n.position.x, y: n.position.y },
      config: n.data.config,
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      condition: (e.data?.condition as string | null | undefined) ?? null,
    })),
  }
}

export function nextNodeId(nodes: AtlasNode[]): string {
  let max = 0
  for (const node of nodes) {
    const match = node.id.match(/^n(\d+)$/)
    if (match) max = Math.max(max, Number(match[1]))
  }
  return `n${max + 1}`
}

export type SaveMeta = {
  name: string
  description: string
  max_runs_per_hour?: number
  budget_usd_per_run?: number | null
}

export function useGraph(initial: WorkflowGraph) {
  const flow = toFlow(initial)
  const [nodes, setNodes] = useState<AtlasNode[]>(flow.nodes)
  const [edges, setEdges] = useState<Edge[]>(flow.edges)
  const [dirty, setDirty] = useState(false)

  const markDirty = useCallback(() => setDirty(true), [])

  const addNode = useCallback(
    (nodeType: string, position: { x: number; y: number }) => {
      setNodes((prev) => [
        ...prev,
        {
          id: nextNodeId(prev),
          type: 'atlas' as const,
          position,
          data: { nodeType, config: {} },
        },
      ])
      setDirty(true)
    },
    [],
  )

  const deleteNode = useCallback((id: string) => {
    setNodes((prev) => prev.filter((n) => n.id !== id))
    setEdges((prev) => prev.filter((e) => e.source !== id && e.target !== id))
    setDirty(true)
  }, [])

  const updateNodeConfig = useCallback(
    (id: string, config: Record<string, unknown>) => {
      setNodes((prev) =>
        prev.map((n) => (n.id === id ? { ...n, data: { ...n.data, config } } : n)),
      )
      setDirty(true)
    },
    [],
  )

  const setGraph = useCallback((graph: WorkflowGraph) => {
    const next = toFlow(graph)
    setNodes(next.nodes)
    setEdges(next.edges)
    setDirty(false)
  }, [])

  const save = useCallback(
    async (workflowId: number, meta: SaveMeta): Promise<number> => {
      const workflow = await api.put<Workflow>(`/api/workflows/${workflowId}`, {
        ...meta,
        graph: fromFlow(nodes, edges),
      })
      setDirty(false)
      return workflow.version
    },
    [nodes, edges],
  )

  return {
    nodes,
    edges,
    setNodes,
    setEdges,
    dirty,
    markDirty,
    addNode,
    deleteNode,
    updateNodeConfig,
    setGraph,
    save,
  }
}
