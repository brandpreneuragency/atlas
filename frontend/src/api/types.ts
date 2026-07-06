export type HealthResponse = {
  status: string
  db: string
  hermes: {
    runs_api: string
  }
  version: string
}

export type EventKind =
  | 'run.started'
  | 'run.step_started'
  | 'run.step_finished'
  | 'run.waiting_approval'
  | 'run.finished'
  | 'run.failed'
  | 'hermes.run_event'
  | 'hermes.cron_changed'
  | 'hermes.error'
  | 'file.changed'
  | 'file.created'
  | 'file.deleted'
  | 'approval.requested'
  | 'approval.resolved'
  | 'review.decided'
  | 'system.killswitch'
  | 'system.login'
  | 'system.error'
  | string

export type AtlasEvent = {
  id: number
  ts: string
  kind: EventKind
  source: string
  agent_id?: number | null
  workflow_id?: number | null
  run_id?: number | null
  payload: { summary: string } & Record<string, unknown>
}

export type AgentStatus = {
  id: number
  name: string
  kind: string
  runs_url: string
  admin_url: string | null
  api_key_env: string
  enabled: boolean
  created_at: string
  status: 'ok' | 'unreachable' | string
  model: string | null
  active_runs: number
  health: Record<string, unknown> | null
}

export type HermesSession = {
  id: string
  title?: string
  updated_at?: number
  source?: 'cron' | 'chat' | 'api' | string
} & Record<string, unknown>

export type ChatMessage = {
  role: 'user' | 'assistant' | 'system' | 'tool' | string
  content: string
} & Record<string, unknown>
export type WorkflowNode = {
  id: string
  type: string
  position: { x: number; y: number }
  config: Record<string, unknown>
}

export type WorkflowEdge = {
  id: string
  source: string
  target: string
  condition: string | null
}

export type WorkflowGraph = {
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
}

export type Workflow = {
  id: number
  name: string
  description: string
  graph: WorkflowGraph
  enabled: boolean
  version: number
  max_runs_per_hour: number
  budget_usd_per_run: number | null
  created_at: string
  updated_at: string
}

export type WorkflowVersion = {
  id: number
  workflow_id: number
  version: number
  created_at: string
}

export type RunStep = {
  id: number
  node_id: string
  node_type: string
  status: 'pending' | 'running' | 'waiting_approval' | 'succeeded' | 'failed' | 'skipped' | string
  input: Record<string, unknown>
  output: Record<string, unknown>
  error: string | null
  cost_usd: number
  started_at: string | null
  finished_at: string | null
}

export type WorkflowRun = {
  id: number
  workflow_id: number
  status:
    | 'queued'
    | 'running'
    | 'waiting_approval'
    | 'succeeded'
    | 'failed'
    | 'cancelled'
    | 'budget_exceeded'
    | string
  trigger_kind: string
  trigger_payload: Record<string, unknown>
  dry_run: boolean
  error: string | null
  cost_usd: number
  tokens_in: number
  tokens_out: number
  created_at: string
  started_at: string | null
  finished_at: string | null
  steps?: RunStep[]
}

export type Approval = {
  id: number
  run_id: number | null
  step_id: number | null
  kind: string
  external_ref: string | null
  message: string
  status: 'pending' | 'approved' | 'rejected' | 'expired' | string
  requested_at: string
  resolved_at: string | null
  resolved_via: string | null
}
