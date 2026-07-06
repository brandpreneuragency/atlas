# ATLAS Control Implementation Plan — MASTER PLAN

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute ONE phase file at a time (`docs/phases/PHASE_N.md`). This master plan is the contract reference — read it fully before any phase, never contradict it.

**Goal:** A single authenticated dashboard on the VPS that monitors and controls the entire ATLAS system: Hermes agent, all automation (ours + Hermes-native cron), files, models/providers, approvals, and the brain review queue.

**Architecture:** One Docker container: FastAPI (Python 3.12) serves `/api/*` and the built React SPA. SQLite (WAL) for operational state. Two Hermes adapters (`HermesClient` → :8642 bearer API, `HermesAdmin` → :9119 token-scraped dashboard API) over a shared `atlas_net` Docker network. Own workflow orchestrator (APScheduler cron + watchfiles file-drop + webhook + manual triggers). SSE pushes a unified event feed to the browser. Caddy (existing `tabs_caddy_1`) terminates TLS on `atlas.<domain>`.

**Tech Stack:** FastAPI ≥0.115, uvicorn, SQLAlchemy 2 (async) + aiosqlite, APScheduler 3.10, httpx, sse-starlette, watchfiles, argon2-cffi, itsdangerous, python-frontmatter, aiosmtplib, pydantic v2 + pydantic-settings · React 18 + TypeScript 5 + Vite 6, react-router-dom 6, TanStack Query 5, zustand 4, @xyflow/react 12, Tailwind CSS 3, @uiw/react-codemirror, react-markdown · pytest + pytest-asyncio + respx · vitest + @testing-library/react · ruff + mypy + eslint + prettier.

---

## 1. Read-me-first rules for builder agents

1. **TDD is mandatory.** Every task: write the failing test → run it, see it fail → implement minimally → run it, see it pass → commit. Never mark a step done without pasting the actual command output into your reasoning.
2. **No invention.** If a contract (schema, route, signature) is defined here, use it verbatim. If something is genuinely undefined, stop and add a `DECISION NEEDED` line to `docs/PROGRESS.md` instead of guessing.
3. **Scope fence.** Only touch files listed in the current task. Never refactor unrelated code.
4. **Secrets.** Never print, log, or commit `API_SERVER_KEY`, password hashes, or `.env` contents. Tests use fake keys.
5. **QA gate.** At the end of every phase run `make check` (backend: ruff + mypy + pytest; frontend: eslint + tsc --noEmit + vitest + vite build) and fix all failures autonomously before declaring the phase complete.
6. **Progress protocol.** After each completed task AND at phase end, update `docs/PROGRESS.md` (format in §9). The user resumes sessions with: *"Read CLAUDE.md, docs/PROGRESS.md, and docs/MASTER_PLAN.md. Continue with the next phase. Run acceptance criteria when done."*
7. **Commits.** Small, per task, conventional messages (`feat:`, `fix:`, `test:`, `chore:`). Never `--no-verify`.
8. **VPS caution.** Read-only inspection over SSH is always fine. Mutating server state (docker, Caddy, DNS) happens ONLY in steps that explicitly say so. NEVER restart the `hermes` container unless the phase step explicitly authorizes it (known restart risk: the venv `hermes` entry script is missing on the live container).

## 2. Repository layout (create exactly this)

```
atlas-control/
├── CLAUDE.md                    # builder rules digest + resume command
├── Makefile                     # check, dev, build, deploy targets
├── docs/
│   ├── MASTER_PLAN.md           # this file (copied from ATLAS)
│   ├── PROGRESS.md
│   └── phases/PHASE_0.md … PHASE_8.md
├── backend/
│   ├── pyproject.toml           # uv-managed
│   ├── app/
│   │   ├── main.py              # app factory, static mount, routers, lifespan
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── db.py                # engine, session factory, WAL init, migrations
│   │   ├── models.py            # ALL ORM models (single file, small project)
│   │   ├── auth.py              # login/logout, argon2, cookie, rate limit, CSRF
│   │   ├── events.py            # append_event() + Broadcaster (SSE fan-out)
│   │   ├── routers/
│   │   │   ├── system.py        # /api/health /api/me /api/killswitch
│   │   │   ├── events.py        # /api/events (list) /api/events/stream (SSE)
│   │   │   ├── agents.py        # /api/agents CRUD + status fan-in
│   │   │   ├── files.py         # /api/files/*
│   │   │   ├── hermes.py        # /api/hermes/* (sessions, chat, cron, models, env, analytics, logs) + /hermes proxy
│   │   │   ├── workflows.py     # /api/workflows /api/runs /api/hooks
│   │   │   ├── approvals.py     # /api/approvals
│   │   │   └── review.py        # /api/review (brain queue)
│   │   ├── hermes/
│   │   │   ├── client.py        # HermesClient (:8642)
│   │   │   ├── admin.py         # HermesAdmin (:9119, token bootstrap)
│   │   │   └── schemas.py       # pydantic models for Hermes payloads
│   │   ├── files/safe_path.py   # path jail (security-critical)
│   │   ├── engine/
│   │   │   ├── engine.py        # run executor
│   │   │   ├── nodes.py         # node executor registry
│   │   │   ├── triggers.py      # scheduler + watcher + webhook glue
│   │   │   ├── guards.py        # provenance, circuit breaker, budgets, kill switch
│   │   │   └── mock.py          # MockHermes for dry-run + tests
│   │   ├── notify/telegram.py   # + notify/email.py
│   │   └── review/service.py    # frontmatter parse, approve/reject actions
│   └── tests/                   # mirrors app/ structure; conftest.py has fixtures
├── frontend/
│   ├── package.json  vite.config.ts  tailwind.config.js  tsconfig.json
│   └── src/
│       ├── main.tsx  App.tsx  routes.tsx
│       ├── api/client.ts        # typed fetch wrapper (credentials, CSRF header, error normalization)
│       ├── api/types.ts         # mirrors backend response models
│       ├── stores/useSession.ts # zustand: auth state, kill switch, SSE connection
│       ├── lib/sse.ts           # EventSource wrapper w/ reconnect + backoff
│       ├── pages/ (Login, MissionControl, Files, Automation, WorkflowEditor,
│       │          RunDetail, Agent, Sessions, Models, Inbox, Review, Settings)
│       └── components/ (feed/, cards/, files/, flow/, ui/)
└── deploy/
    ├── Dockerfile               # stage1 node:20 build SPA → stage2 python:3.12-slim
    ├── docker-compose.yml       # service atlas_control, atlas_net external
    ├── Caddyfile.snippet        # site block to append on server
    └── backup.sh                # nightly sqlite VACUUM INTO + tar
```

## 3. Environment & configuration contract

`backend/app/config.py` → `Settings` (pydantic-settings, env prefix `ATLAS_`):

| Env var | Default | Meaning |
|---|---|---|
| `ATLAS_DATA_DIR` | `/data` | SQLite + runtime state volume |
| `ATLAS_ATLAS_ROOT` | `/opt/atlas` | mounted ATLAS tree (the file-manager jail root) |
| `ATLAS_HERMES_RUNS_URL` | `http://hermes:8642` | HermesClient base |
| `ATLAS_HERMES_ADMIN_URL` | `http://hermes:9119` | HermesAdmin base |
| `ATLAS_HERMES_API_KEY` | — (required) | bearer for :8642 (same value as Hermes `API_SERVER_KEY`) |
| `ATLAS_PASSWORD` | — (required first boot) | bootstrap login password; hashed into DB then ignorable |
| `ATLAS_SECRET_KEY` | — (required) | cookie signing (openssl rand -hex 32) |
| `ATLAS_TZ` | `Europe/Istanbul` | cron display + schedule timezone |
| `ATLAS_PORT` | `8700` | bind port (0.0.0.0 in-container; never published publicly) |
| `ATLAS_STATIC_DIR` | `/app/static` | built SPA dir the backend serves (dev: unset → static mount skipped) |
| `ATLAS_MOCK_HERMES` | `0` | `1` swaps HermesClient for MockHermes (dev/tests only) |
| `ATLAS_DEV_MODE` | `0` | `1` relaxes cookie `Secure` flag for local http; MUST be `0`/unset in prod |
| `ATLAS_PUBLIC_URL` | `https://atlas.<domain>` | base URL used in notification links (Phase 7) |

Dev mode: `.env.dev` with `ATLAS_ATLAS_ROOT=./devdata/atlas`, `ATLAS_DATA_DIR=./devdata`, `ATLAS_DEV_MODE=1`, MockHermes enabled via `ATLAS_MOCK_HERMES=1`. `Settings.dev_mode` / `Settings.mock_hermes` are the parsed booleans used in code.

## 4. Database schema (SQLite, executed by `db.py` migration runner)

Migration style: numbered SQL files in `backend/app/migrations/00X_*.sql`, applied in order, tracked in table `schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)`. `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;` on every connection.

```sql
-- 001_core.sql
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE agents (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL DEFAULT 'hermes',
  runs_url TEXT NOT NULL, admin_url TEXT, api_key_env TEXT NOT NULL DEFAULT 'ATLAS_HERMES_API_KEY',
  enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE events (
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL,
  agent_id INTEGER, workflow_id INTEGER, run_id INTEGER, payload TEXT NOT NULL DEFAULT '{}');
CREATE INDEX idx_events_ts ON events(ts DESC);
CREATE INDEX idx_events_kind ON events(kind);
-- 002_workflows.sql
CREATE TABLE workflows (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  graph TEXT NOT NULL,                 -- JSON, schema §6
  enabled INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
  max_runs_per_hour INTEGER NOT NULL DEFAULT 6, budget_usd_per_run REAL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE workflow_versions (
  id INTEGER PRIMARY KEY, workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  version INTEGER NOT NULL, graph TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(workflow_id, version));
CREATE TABLE runs (
  id INTEGER PRIMARY KEY, workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'queued',  -- queued|running|waiting_approval|succeeded|failed|cancelled|budget_exceeded
  trigger_kind TEXT NOT NULL, trigger_payload TEXT NOT NULL DEFAULT '{}',
  dry_run INTEGER NOT NULL DEFAULT 0, error TEXT,
  cost_usd REAL NOT NULL DEFAULT 0, tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT);
CREATE TABLE run_steps (
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  node_id TEXT NOT NULL, node_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', -- pending|running|waiting_approval|succeeded|failed|skipped
  input TEXT NOT NULL DEFAULT '{}', output TEXT NOT NULL DEFAULT '{}', error TEXT,
  cost_usd REAL NOT NULL DEFAULT 0, started_at TEXT, finished_at TEXT);
CREATE TABLE approvals (
  id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
  step_id INTEGER REFERENCES run_steps(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,                  -- gate|hermes_run
  external_ref TEXT,                   -- hermes run_id for kind=hermes_run
  message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', -- pending|approved|rejected|expired
  requested_at TEXT NOT NULL, resolved_at TEXT, resolved_via TEXT);
CREATE TABLE chat_threads (
  id INTEGER PRIMARY KEY, hermes_session_id TEXT NOT NULL, agent_id INTEGER NOT NULL,
  title TEXT NOT NULL DEFAULT 'New chat', created_at TEXT NOT NULL);
```

`settings` keys used: `password_hash`, `global_pause` (`"0"|"1"`), `telegram_bot_token`, `telegram_chat_id`, `smtp_url`, `smtp_to`, `shell_allowlist` (JSON array), `webhook_secrets` are stored inside workflow graph config, not here.

## 5. Backend API surface (ours)

All routes under `/api`, JSON, session-cookie auth except `POST /api/auth/login`, `GET /api/health`, `POST /api/hooks/*`. Mutating routes require header `X-Atlas-CSRF: 1` (rejected with 403 otherwise). Errors: `{"detail": str}` with proper status codes.

```
POST /api/auth/login {password} → 204 + Set-Cookie   | 401; rate limit 5/5min/IP → 429
POST /api/auth/logout → 204
GET  /api/me → {authenticated: true}
GET  /api/health → {status, db, hermes: {runs_api, admin_api}, version}
GET  /api/killswitch → {paused: bool}     POST /api/killswitch {paused} → pauses engine + Hermes crons
GET  /api/events?limit&before_id&kind → Event[]      GET /api/events/stream → SSE (event: atlas, data: Event JSON)
GET  /api/agents → AgentStatus[] (config + live health + active run + model info)
GET  /api/files/tree?path= → {entries: [{name,is_dir,size,mtime}]}   (path relative to jail root)
GET  /api/files/read?path= → {content, mtime, truncated}   (>2MB → 413)
PUT  /api/files/write {path, content, expected_mtime|null} → 204 | 409 mtime conflict
POST /api/files/mkdir|move|copy|delete {path(s), dest?} → 204 (delete of non-empty dir requires {recursive:true})
POST /api/files/upload (multipart) → 201
GET  /api/hermes/sessions?q&limit / /api/hermes/sessions/{sid} / {sid}/messages → proxied via HermesClient
POST /api/hermes/chat {thread_id|null, message} → SSE stream of tokens (creates thread on first message)
GET|POST|PUT|DELETE /api/hermes/cron[...]   pause/resume/trigger → proxied via HermesAdmin
GET  /api/hermes/model / model/options    POST /api/hermes/model {model, provider}
GET  /api/hermes/env (masked) PUT /api/hermes/env {key, value} DELETE /api/hermes/env/{key}
GET  /api/hermes/analytics/usage|models   GET /api/hermes/logs?tail=
ANY  /hermes/{path:path} → raw reverse proxy to admin_url (auth required; streaming passthrough)
GET|POST /api/workflows   GET|PUT|DELETE /api/workflows/{id}   POST /api/workflows/{id}/enable {enabled}
GET  /api/workflows/{id}/versions   POST /api/workflows/{id}/rollback {version}
POST /api/workflows/{id}/run {dry_run: bool, payload?} → {run_id}
GET  /api/runs?workflow_id&status&limit → Run[]   GET /api/runs/{id} → Run + steps
POST /api/runs/{id}/cancel → 204
POST /api/hooks/{workflow_id}/{secret} → 202 {run_id}   (no session; secret from trigger config; 404 on mismatch)
GET  /api/approvals?status= → Approval[]   POST /api/approvals/{id}/resolve {decision: approved|rejected}
GET  /api/review → ReviewItem[] (parsed pending notes)   POST /api/review/{name}/decide {decision} → {run_id}
GET|PUT /api/settings/notifications   POST /api/settings/password {current, new}
```

## 6. Workflow graph JSON contract

```json
{
  "nodes": [
    {"id": "n1", "type": "trigger.cron", "position": {"x": 0, "y": 0},
     "config": {"expr": "0 7 * * *"}},
    {"id": "n2", "type": "hermes.task", "position": {"x": 260, "y": 0},
     "config": {"prompt": "Summarize {{trigger.file_path}}", "context_files": [],
                "session_key": null, "timeout_s": 900, "retries": 1}},
    {"id": "n3", "type": "gate.approval", "position": {"x": 520, "y": 0},
     "config": {"message": "Publish digest?", "timeout_h": 24, "notify": ["telegram"]}},
    {"id": "n4", "type": "file.op", "position": {"x": 780, "y": 0},
     "config": {"op": "write", "path": "04_reports/digest.md", "content": "{{n2.output_text}}"}}
  ],
  "edges": [
    {"id": "e1", "source": "n1", "target": "n2", "condition": null},
    {"id": "e2", "source": "n2", "target": "n3", "condition": null},
    {"id": "e3", "source": "n3", "target": "n4", "condition": "approved"}
  ]
}
```

Node type registry (all v1 types + config schemas) is defined once in `backend/app/engine/nodes.py` and mirrored in `frontend/src/api/types.ts`:

| type | config fields | output context |
|---|---|---|
| `trigger.cron` | `expr` (5-field cron) | `{fired_at}` |
| `trigger.file_drop` | `watch_path` (rel dir), `glob` (default `*`), `stability_s` (default 5) | `{file_path}` |
| `trigger.webhook` | `secret` (server-generated, shown once) | `{body}` (JSON) |
| `trigger.manual` | — | `{payload}` |
| `hermes.task` | `prompt` (templated), `context_files[]`, `session_key`, `timeout_s`, `retries` | `{output_text, hermes_run_id, usage}` |
| `file.op` | `op: move|copy|write|delete|mkdir`, `path`, `dest?`, `content?` (templated) | `{path}` |
| `logic.condition` | `expression` (safe subset: `ctx['n2']['output_text']`-style lookups + comparisons via `simpleeval`-like evaluator we write) | branch label `true|false` |
| `notify.telegram` | `message` (templated) | `{}` |
| `notify.email` | `subject`, `message` (templated) | `{}` |
| `shell.command` | `command` (must prefix-match an entry in settings `shell_allowlist`), `cwd` (rel, jailed), `timeout_s` | `{stdout, exit_code}` |
| `gate.approval` | `message`, `timeout_h`, `notify[]` | edge conditions `approved|rejected` |

Templating: `{{trigger.x}}` and `{{<node_id>.<field>}}` substitution only (regex replace from the run context dict; no eval).

## 7. Hermes adapter contracts

```python
class HermesClient:            # base = ATLAS_HERMES_RUNS_URL, auth = Bearer ATLAS_HERMES_API_KEY
    async def health(self) -> dict                     # GET /health/detailed
    async def capabilities(self) -> dict               # GET /v1/capabilities
    async def create_run(self, prompt: str, *, session_key: str | None = None) -> str   # POST /v1/runs → run_id (202)
    async def run_status(self, run_id: str) -> dict    # GET /v1/runs/{id}
    async def run_events(self, run_id: str) -> AsyncIterator[dict]   # GET /v1/runs/{id}/events (SSE lines → dict)
    async def approve_run(self, run_id: str, approval_id: str, decision: str) -> None
    async def stop_run(self, run_id: str) -> None
    async def sessions(self, q: str | None = None, limit: int = 50) -> list[dict]   # GET /api/sessions
    async def session_messages(self, sid: str) -> list[dict]
    async def chat_stream(self, sid: str, message: str) -> AsyncIterator[str]        # POST /api/sessions/{sid}/chat/stream
    async def create_session(self) -> str

class HermesAdmin:             # base = ATLAS_HERMES_ADMIN_URL; token scraped from GET / HTML, cached, refreshed on 401
    async def _token(self) -> str                      # regex r'"token"\s*[:=]\s*"([A-Za-z0-9_-]{20,})"' over index HTML;
                                                       # exact pattern pinned in Phase 0 against live HTML, recorded in PROGRESS.md
    async def cron_jobs(self) -> list[dict]            # GET /api/cron/jobs
    async def cron_create(self, job: dict) -> dict     # POST /api/cron/jobs   (shape mirrors /home/admin/.hermes/cron/jobs.json entries)
    async def cron_update(self, job_id: str, patch: dict) -> dict
    async def cron_pause / cron_resume / cron_trigger / cron_delete(self, job_id: str)
    async def model_info / model_options / model_set(...)
    async def env_list(self) -> list[dict]             # GET /api/env (values masked by Hermes)
    async def env_put(self, key: str, value: str) / env_delete(self, key: str)
    async def analytics_usage / analytics_models(self) -> dict
    async def logs(self, tail: int = 200) -> str
    async def gateway_restart(self) -> None            # POST /api/gateway/restart — ONLY from kill-switch/settings flows
```

Both adapters: 10s default timeout (runs/chat streams excluded), raise `HermesUnavailable(detail)` on connect errors; routers translate to 502 with the detail; every adapter failure appends a `hermes.error` event.

## 8. Event kinds (unified feed)

`kind` values: `run.started|run.step_started|run.step_finished|run.waiting_approval|run.finished|run.failed`, `hermes.run_event` (relayed lifecycle), `hermes.cron_changed`, `hermes.error`, `file.changed|file.created|file.deleted` (from file-manager actions and watcher), `approval.requested|approval.resolved`, `review.decided`, `system.killswitch`, `system.login`, `system.error`. Payload always includes human-readable `summary` string — the feed renders `summary` + timestamp + links (`run_id`/`workflow_id`/path).

## 9. PROGRESS.md format

```markdown
# Progress
## Current: Phase N — <name> (task N.M in progress)
## Done
- [x] Phase 0 — completed 2026-07-08 (all acceptance criteria pass)
- [x] Task 1.1 login backend — commit abc123
## Decisions / deviations
- 2026-07-08: token regex pinned to `...` (Phase 0 Task 0.4)
## DECISION NEEDED
- (none)
```

## 10. Mock data contract (MockHermes)

`backend/app/engine/mock.py` implements the `HermesClient` interface without network. Used by unit tests and dry-run mode. Behavior: `create_run` returns `"mock-run-<n>"`; `run_events` yields `{"type":"run.started"}`, `{"type":"tool_progress","summary":"mock tool"}`, `{"type":"run.completed","output_text":"MOCK OUTPUT for: <first 40 chars of prompt>","usage":{"input_tokens":100,"output_tokens":50}}` with 0 delay; `run_status` returns `{"status":"completed","output_text":...}`. Frontend dev fixtures live in `frontend/src/api/fixtures.ts` and mirror §5 response shapes exactly.

## 11. Deployment topology & names (fixed)

- Docker network: `atlas_net` (external, created in Phase 0; `hermes` and `tabs_caddy_1` are connected to it).
- Service/container: `atlas_control`; volumes: `atlas_control_data:/data`, `/home/admin/atlas:/opt/atlas`.
- Server env file: `/home/admin/atlas-control/.env` (chmod 600) — never in git.
- Caddy site: `atlas.<domain>` → `reverse_proxy http://atlas_control:8700`. Domain confirmed in Phase 0 (family: brandpreneur.net).
- Deploy flow (Makefile `deploy`): `git pull` on server + `docker compose build && docker compose up -d` in `/home/admin/atlas-control/` (repo cloned on server), then `curl -f https://atlas.<domain>/api/health`.
- Hermes image gets pinned by digest `nousresearch/hermes-agent@sha256:b6e41c155d6bfce5ad83c5d0fec670086db8a43250e4511c9474134be5482d33` (Phase 0).

## 12. Risk register (mitigations are plan tasks)

| Risk | Mitigation (phase) |
|---|---|
| 9119 token scrape breaks on Hermes update | pinned image digest; adapter isolates scrape in one function w/ regex recorded in PROGRESS.md; contract test hits live API in Phase 0/2 (P0, P2) |
| hermes container restart failure (missing venv script) | verify before any restart; never auto-restart (P0) |
| Trigger loops / event storms | provenance guard, stability window, circuit breaker + tests (P5) |
| Rate limits (already observed 429s) | queue-of-1, global semaphore 2, budgets, telemetry (P5), analytics page (P4) |
| Path traversal | `safe_path.py` jail + adversarial tests, all file routes go through it (P3) |
| Sync conflicts on edits | mtime optimistic concurrency 409 flow (P3) |
| Lesser-model drift | this plan format, `make check` gates, PROGRESS.md protocol (all) |
| No backups | nightly backup.sh + restore runbook (P8) |

## 13. Phase index

| Phase | File | Delivers |
|---|---|---|
| 0 | PHASE_0.md | VPS prep, network, domain, repo scaffold, live API contract capture |
| 1 | PHASE_1.md | Walking skeleton: auth + SPA shell + Docker + Caddy, live at https://atlas.<domain>, /hermes proxy |
| 2 | PHASE_2.md | Event backbone + SSE + Hermes adapters + Mission Control (cards, feed) + session browser |
| 3 | PHASE_3.md | File manager (jail, tree, edit, upload, bulk, conflicts) |
| 4 | PHASE_4.md | Control plane: cron federation, models/providers page, analytics, kill switch v1 |
| 5 | PHASE_5.md | Workflow engine backend (nodes, triggers, guards, budgets, run API) |
| 6 | PHASE_6.md | Canvas builder UI, run panel, dry-run, versions, cron migration |
| 7 | PHASE_7.md | Approval inbox, Telegram/email, brain review queue |
| 8 | PHASE_8.md | Hardening: backups, rate limits, ops polish, final acceptance |
