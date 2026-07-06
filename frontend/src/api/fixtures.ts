import type { AgentStatus, AtlasEvent, HermesSession, ChatMessage } from './types'

export const fixtureEvents: AtlasEvent[] = [
  {
    id: 3,
    ts: new Date(Date.now() - 1 * 60_000).toISOString(),
    kind: 'system.login',
    source: 'auth',
    payload: { summary: 'admin signed in' },
  },
  {
    id: 2,
    ts: new Date(Date.now() - 5 * 60_000).toISOString(),
    kind: 'hermes.run_event',
    source: 'chat',
    payload: { summary: 'chat reply (12 chars)', session_id: 'sess-1' },
  },
  {
    id: 1,
    ts: new Date(Date.now() - 12 * 60_000).toISOString(),
    kind: 'run.started',
    source: 'engine',
    workflow_id: 1,
    payload: { summary: 'Digest workflow started' },
  },
]

export const fixtureAgent: AgentStatus = {
  id: 1,
  name: 'Hermes',
  kind: 'hermes',
  runs_url: 'http://hermes:8642',
  admin_url: 'http://hermes:9119',
  api_key_env: 'ATLAS_HERMES_API_KEY',
  enabled: true,
  created_at: '2026-07-06T00:00:00Z',
  status: 'ok',
  model: 'gpt-5.5',
  active_runs: 1,
  health: { status: 'ok' },
}

export const fixtureAgentUnreachable: AgentStatus = {
  ...fixtureAgent,
  status: 'unreachable',
  active_runs: 0,
  model: null,
  health: null,
}

export const fixtureSessions: HermesSession[] = [
  { id: 'sess-1', title: 'App Store Market Scout', updated_at: 1783300012, source: 'cron' },
  { id: 'sess-2', title: 'Reply PONG', updated_at: 1783290000, source: 'chat' },
  { id: 'sess-3', title: 'API run from curl', updated_at: 1783200000, source: 'api' },
]

export const fixtureMessages: ChatMessage[] = [
  { role: 'user', content: 'Reply PONG' },
  { role: 'assistant', content: 'PONG' },
  { role: 'tool', content: '{"name":"web_search","result":"..."}' },
]