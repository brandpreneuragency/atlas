import { CATEGORY_COLORS, NODE_META } from './nodeTypes'

/** Left drawer: drag a node type onto the canvas (React Flow onDrop pattern). */
export function NodePalette() {
  return (
    <aside
      data-testid="node-palette"
      className="w-44 shrink-0 space-y-2 overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-3"
    >
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
        Nodes
      </h3>
      {Object.entries(NODE_META).map(([type, meta]) => (
        <div
          key={type}
          draggable
          data-testid={`palette-${type}`}
          onDragStart={(event) => {
            event.dataTransfer.setData('application/atlas-node', type)
            event.dataTransfer.effectAllowed = 'move'
          }}
          className={`cursor-grab rounded-lg border px-2 py-1.5 text-xs text-slate-200 ${CATEGORY_COLORS[meta.category]}`}
        >
          <span aria-hidden className="mr-1">
            {meta.icon}
          </span>
          {meta.label}
        </div>
      ))}
    </aside>
  )
}
