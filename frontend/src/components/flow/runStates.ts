import type { AtlasEvent } from '../../api/types'
import type { RunNodeState } from './nodeTypes'

export type RunNodeStates = Record<string, RunNodeState>

/** Fold a feed event into the per-node visual state map (keyed by node id). */
export function applyRunEvent(states: RunNodeStates, event: AtlasEvent): RunNodeStates {
  const nodeId = event.payload.node_id
  if (typeof nodeId !== 'string') return states
  switch (event.kind) {
    case 'run.step_started':
      return { ...states, [nodeId]: 'running' }
    case 'run.step_finished': {
      const status = event.payload.status === 'failed' ? 'failed' : 'succeeded'
      return { ...states, [nodeId]: status }
    }
    case 'run.waiting_approval':
      return { ...states, [nodeId]: 'waiting' }
    default:
      return states
  }
}
