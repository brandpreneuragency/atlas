# Progress — ATLAS Control

> This file is the resume anchor. Builder agents update it after every completed task and at phase end.
> Resume command: **"Read CLAUDE.md, docs/PROGRESS.md, and docs/MASTER_PLAN.md. Continue with the next phase. Run acceptance criteria when done."**

## Current
Phase 1 — IN PROGRESS (Tasks 1.1–1.4 complete; Task 1.5 next).

## Done
- [x] Planning: design spec + master plan + phases 0–8 + execution playbook written and approved (2026-07-06).
- [x] Task 0.1 — server audit: hermes Up (digest sha256:b6e41c...), 265G free, 30G RAM. Restart-safety issue CONFIRMED (venv `hermes` entry script count = 0 → do NOT restart hermes container).
- [x] Task 0.2 — image pinned as `hermes-pinned:v0.16.0`; `atlas_net` created; `hermes` + `tabs_caddy_1` connected; in-network reachability verified (hermes:9119/api/status → 200, hermes:8642/health → ok).
- [x] Task 0.3 — full Hermes API contract captured to `02_dev_plan/phase0_captures/` (hermes-runs-contract.md, hermes-admin-contract.md, hermes-contract.json). Derived runs API from source to avoid burning the 429-limited quota.
- [x] Task 0.4 — Caddy/domain: site configured for `atlas.brandpreneur.net`; Caddy reloaded; Let’s Encrypt certificate issued; HTTPS returns expected 502.
- [x] Task 0.5 — repo scaffold created at `C:\dev\atlas-control`; plan docs copied; sanitized Phase-0 fixtures copied to `backend/tests/fixtures/`; backend/frontend sanity checks pass; pushed to `https://github.com/brandpreneuragency/atlas`; server clone exists at `/home/admin/atlas-control`.
- [x] Task 1.1 — Settings + DB core: `Settings`, SQLite async engine/session, WAL/foreign-key pragmas, migration runner, and `001_core.sql` implemented. Checks: `uv run ruff check .`, `uv run mypy app`, `uv run pytest -q` all pass.
- [x] Task 1.2 — Auth/session/CSRF/rate-limit/system routes implemented: first-boot password hashing, login/logout, signed `atlas_session` cookie, API auth middleware, CSRF middleware, public `/api/health`, `/api/me`, and killswitch settings. Checks: `uv run ruff check .`, `uv run mypy app`, `uv run pytest -q` all pass.
- [x] Task 1.3 — `HermesClient.health()` and `capabilities()` implemented with bearer auth, 10s default timeout, `HermesUnavailable` translation, and `/api/health` real-mode degradation. Checks: `uv run ruff check .`, `uv run mypy app`, `uv run pytest -q` all pass.
- [x] Task 1.4 — `/hermes/{path}` authenticated reverse-proxy stopgap implemented for HTTP methods with hop-by-hop header stripping and websocket 501 limitation. Checks: `uv run ruff check .`, `uv run mypy app`, `uv run pytest -q` all pass.

## Phase-0 records (CAPTURED — later phases depend on these)
- **Run POST payload:** `POST /v1/runs {"input": "<prompt>"}` → 202 `{"run_id":"run_<hex>","status":"started"}`. (`input` required; may be message-list.)
- **Run terminal event + output field:** SSE field is **`event`** (not `type`); terminal = `run.completed` (also `run.failed`/`run.cancelled`); output text = `output` field; map to internal `output_text`.
- **Run usage fields:** `usage:{input_tokens,output_tokens,total_tokens}` on `run.completed` + on `GET /v1/runs/{id}` when completed.
- **9119 token:** injected as `window.__HERMES_SESSION_TOKEN__="..."`; regex `__HERMES_SESSION_TOKEN__\s*=\s*"([A-Za-z0-9_-]+)"`; header `Authorization: Bearer`; rotates per boot → cache + re-scrape on 401. `/api/status` public.
- **Host-header behavior:** `http://hermes:9119` accepted (200) over atlas_net — NO `Host:` override needed.
- **Subdomain chosen + DNS confirmed:** `atlas.brandpreneur.net` → `142.132.230.137`; Caddy issued a valid certificate; `https://atlas.brandpreneur.net/` returns expected `502` until the Phase-1 app container exists.
- **Caddyfile mount:** `/home/admin/tabs/Caddyfile` → `/etc/caddy/Caddyfile` (Task 0.4 Step 1 verified).

## Decisions / deviations
- 2026-07-06: Derived the runs API contract from `api_server.py` source instead of a live run — the model has an active 429 usage-limit and source is authoritative. No quota spent.
- 2026-07-06: `/api/cron/jobs` returns a **bare JSON array**, not `{"jobs":[]}`. Adapter parses a list.
- 2026-07-06: Only **ONE** Hermes cron job exists now (`App Store Market Scout`, paused, 429). The stale runtime doc's second "Digest Append" job is gone. Phase 6 migration proof targets the single job.
- 2026-07-06: `/api/env` is a **dict keyed by var name** with `{is_set,redacted_value,is_password,category,tools,...}`, not a flat list. Models provider-keys panel renders this shape.
- 2026-07-06: `relaxed_turing` orphan container removed after user approval (`docker rm -f relaxed_turing`).
- 2026-07-06: `make` is not installed in this Windows PowerShell environment; equivalent backend/frontend commands were run directly and passed. Use Git Bash or install make for the literal `make check` gate.
- 2026-07-06: Recovered missing host Caddyfile bind source: `/home/admin/tabs/Caddyfile` had become a directory; recreated it from live Caddy admin config plus the atlas site block, loaded the corrected config from `/tmp/Caddyfile.atlas.new`, and preserved `/home/admin/tabs/Caddyfile.dir-bak-phase0`.

- 2026-07-06: VPS deploy key installed; `/home/admin/atlas-control` cloned successfully from GitHub.

## DECISION NEEDED
- (none)
