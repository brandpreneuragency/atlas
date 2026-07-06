CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE agents (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'hermes',
  runs_url TEXT NOT NULL,
  admin_url TEXT,
  api_key_env TEXT NOT NULL DEFAULT 'ATLAS_HERMES_API_KEY',
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,
  agent_id INTEGER,
  workflow_id INTEGER,
  run_id INTEGER,
  payload TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_events_ts ON events(ts DESC);
CREATE INDEX idx_events_kind ON events(kind);
