-- 002_chat_threads.sql
-- Chat thread registry for /api/hermes/chat. Split out of 002_workflows.sql
-- (MASTER_PLAN §4) because Phase 2 needs chat_threads before the Phase 5
-- workflows/runs/approvals schema. The remaining workflow tables will land as
-- 003_workflows.sql in Phase 5.
CREATE TABLE chat_threads (
  id INTEGER PRIMARY KEY,
  hermes_session_id TEXT NOT NULL,
  agent_id INTEGER NOT NULL,
  title TEXT NOT NULL DEFAULT 'New chat',
  created_at TEXT NOT NULL
);