import {
  Background,
  Controls,
  ReactFlow,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
} from '@xyflow/react'
import type { Connection, Edge, EdgeChange, NodeChange } from '@xyflow/react'
import { useCallback } from 'react'

import '@xyflow/react/dist/style.css'

import { nodeTypes } from './nodeTypes'
import type { AtlasNode } from './useGraph'

type CanvasProps = {
  nodes: AtlasNode[]
  edges: Edge[]
  setNodes: (updater: (prev: AtlasNode[]) => AtlasNode[]) => void
  setEdges: (updater: (prev: Edge[]) => Edge[]) => void
  onDropNode: (nodeType: string, position: { x: number; y: number }) => void
  onSelectNode: (id: string | null) => void
  markDirty: () => void
}

export function Canvas({
  nodes,
  edges,
  setNodes,
  setEdges,
  onDropNode,
  onSelectNode,
  markDirty,
}: CanvasProps) {
  const { screenToFlowPosition } = useReactFlow()

  const onNodesChange = useCallback(
    (changes: NodeChange<AtlasNode>[]) => {
      setNodes((prev) => applyNodeChanges(changes, prev))
      if (changes.some((c) => c.type === 'position' || c.type === 'remove')) markDirty()
    },
    [setNodes, markDirty],
  )

  const onEdgesChange = useCallback(
    (changes: EdgeChange<Edge>[]) => {
      setEdges((prev) => applyEdgeChanges(changes, prev))
      if (changes.some((c) => c.type === 'remove')) markDirty()
    },
    [setEdges, markDirty],
  )

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((prev) =>
        addEdge(
          {
            ...connection,
            id: `e${Date.now()}`,
            data: { condition: null },
          },
          prev,
        ),
      )
      markDirty()
    },
    [setEdges, markDirty],
  )

  return (
    <div className="h-full min-h-[480px] flex-1 rounded-2xl border border-slate-800 bg-slate-950">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onSelectionChange={({ nodes: selected }) =>
          onSelectNode(selected[0]?.id ?? null)
        }
        onDragOver={(event) => {
          event.preventDefault()
          event.dataTransfer.dropEffect = 'move'
        }}
        onDrop={(event) => {
          event.preventDefault()
          const nodeType = event.dataTransfer.getData('application/atlas-node')
          if (!nodeType) return
          onDropNode(
            nodeType,
            screenToFlowPosition({ x: event.clientX, y: event.clientY }),
          )
        }}
        fitView
        colorMode="dark"
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={18} />
        <Controls />
      </ReactFlow>
    </div>
  )
}
