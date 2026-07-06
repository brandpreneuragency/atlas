import { Handle, Position } from '@xyflow/react'
import type { NodeProps } from '@xyflow/react'

import type { AtlasNode } from './useGraph'

export type NodeMeta = {
  label: string
  icon: string
  category: 'trigger' | 'hermes' | 'file' | 'logic' | 'notify' | 'shell' | 'gate'
}

// §6 node registry mirrored client-side (colors per PHASE_6 Task 6.1).
export const NODE_META: Record<string, NodeMeta> = {
  'trigger.cron': { label: 'Cron trigger', icon: '⏰', category: 'trigger' },
  'trigger.file_drop': { label: 'File drop', icon: '📥', category: 'trigger' },
  'trigger.webhook': { label: 'Webhook', icon: '🔗', category: 'trigger' },
  'trigger.manual': { label: 'Manual', icon: '▶️', category: 'trigger' },
  'hermes.task': { label: 'Hermes task', icon: '🤖', category: 'hermes' },
  'file.op': { label: 'File op', icon: '📄', category: 'file' },
  'logic.condition': { label: 'Condition', icon: '🔀', category: 'logic' },
  'notify.telegram': { label: 'Telegram', icon: '📣', category: 'notify' },
  'notify.email': { label: 'Email', icon: '✉️', category: 'notify' },
  'shell.command': { label: 'Shell', icon: '💻', category: 'shell' },
  'gate.approval': { label: 'Approval gate', icon: '🛂', category: 'gate' },
}

export const CATEGORY_COLORS: Record<NodeMeta['category'], string> = {
  trigger: 'border-violet-500 bg-violet-500/10',
  hermes: 'border-blue-500 bg-blue-500/10',
  file: 'border-green-500 bg-green-500/10',
  logic: 'border-amber-500 bg-amber-500/10',
  notify: 'border-cyan-500 bg-cyan-500/10',
  shell: 'border-red-500 bg-red-500/10',
  gate: 'border-orange-500 bg-orange-500/10',
}

/** One-line config summary shown inside the node. */
export function configSummary(nodeType: string, config: Record<string, unknown>): string {
  const str = (key: string) => (typeof config[key] === 'string' ? (config[key] as string) : '')
  switch (nodeType) {
    case 'trigger.cron':
      return str('expr')
    case 'trigger.file_drop':
      return `${str('watch_path')}/${str('glob') || '*'}`
    case 'trigger.webhook':
      return config.secret ? 'secret set' : 'no secret'
    case 'trigger.manual':
      return 'run manually'
    case 'hermes.task':
      return str('prompt').slice(0, 40)
    case 'file.op':
      return `${str('op')} ${str('path')}`.trim()
    case 'logic.condition':
      return str('expression').slice(0, 40)
    case 'notify.telegram':
    case 'notify.email':
      return str('message').slice(0, 40)
    case 'shell.command':
      return str('command').slice(0, 40)
    case 'gate.approval':
      return str('message').slice(0, 40)
    default:
      return ''
  }
}

export type RunNodeState = 'running' | 'succeeded' | 'failed' | 'skipped' | 'waiting'

const STATE_BADGE: Record<RunNodeState, string> = {
  running: '⏳',
  succeeded: '✅',
  failed: '❌',
  skipped: '⤼',
  waiting: '✋',
}

export function AtlasFlowNode({ id, data, selected }: NodeProps<AtlasNode>) {
  const meta = NODE_META[data.nodeType] ?? {
    label: data.nodeType,
    icon: '❓',
    category: 'logic' as const,
  }
  const runState = data.runState as RunNodeState | undefined
  const invalid = Boolean(data.invalid)
  const isTrigger = meta.category === 'trigger'
  return (
    <div
      data-testid={`flow-node-${id}`}
      className={`min-w-40 rounded-xl border-2 px-3 py-2 text-left shadow ${CATEGORY_COLORS[meta.category]} ${
        selected ? 'ring-2 ring-white/60' : ''
      } ${runState === 'running' ? 'animate-pulse' : ''} ${invalid ? 'outline outline-2 outline-red-500' : ''}`}
    >
      {!isTrigger && <Handle type="target" position={Position.Left} />}
      <div className="flex items-center gap-2 text-sm font-medium text-slate-100">
        <span aria-hidden>{meta.icon}</span>
        <span>{meta.label}</span>
        {runState && (
          <span data-testid={`node-state-${id}`} className="ml-auto">
            {STATE_BADGE[runState]}
          </span>
        )}
      </div>
      <div className="mt-1 truncate font-mono text-xs text-slate-400">
        {configSummary(data.nodeType, data.config)}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

export const nodeTypes = { atlas: AtlasFlowNode }
