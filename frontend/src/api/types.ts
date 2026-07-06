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