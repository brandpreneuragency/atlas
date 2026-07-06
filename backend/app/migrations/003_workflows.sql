-- 003_workflows.sql — MASTER_PLAN §4 "002_workflows" minus chat_threads
-- (chat_threads landed early in 002_chat_threads.sql - see PROGRESS.md deviation)
CREATE TABLE workflows (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  graph TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
  max_runs_per_hour INTEGER NOT NULL DEFAULT 6, budget_usd_per_run REAL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE workflow_versions (
  id INTEGER PRIMARY KEY, workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  version INTEGER NOT NULL, graph TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(workflow_id, version));
CREATE TABLE runs (
  id INTEGER PRIMARY KEY, workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'queued',
  trigger_kind TEXT NOT NULL, trigger_payload TEXT NOT NULL DEFAULT '{}',
  dry_run INTEGER NOT NULL DEFAULT 0, error TEXT,
  cost_usd REAL NOT NULL DEFAULT 0, tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT);
CREATE TABLE run_steps (
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  node_id TEXT NOT NULL, node_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  input TEXT NOT NULL DEFAULT '{}', output TEXT NOT NULL DEFAULT '{}', error TEXT,
  cost_usd REAL NOT NULL DEFAULT 0, started_at TEXT, finished_at TEXT);
CREATE TABLE approvals (
  id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
  step_id INTEGER REFERENCES run_steps(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  external_ref TEXT,
  message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  requested_at TEXT NOT NULL, resolved_at TEXT, resolved_via TEXT);
