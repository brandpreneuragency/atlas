# Progress — ATLAS Control

> This file is the resume anchor. Builder agents update it after every completed task and at phase end.
> Resume command: **"Read CLAUDE.md, docs/PROGRESS.md, and docs/MASTER_PLAN.md. Continue with the next phase. Run acceptance criteria when done."**

## Current
Phase 0 — IN PROGRESS (controller session 2026-07-06). Tasks 0.1, 0.2, 0.3 DONE. Task 0.5 scaffold pushed to GitHub. Blocked on DNS propagation for 0.4 and GitHub deploy-key installation for server clone.

## Done
- [x] Planning: design spec + master plan + phases 0–8 + execution playbook written and approved (2026-07-06).
- [x] Task 0.1 — server audit: hermes Up (digest sha256:b6e41c...), 265G free, 30G RAM. Restart-safety issue CONFIRMED (venv `hermes` entry script count = 0 → do NOT restart hermes container).
- [x] Task 0.2 — image pinned as `hermes-pinned:v0.16.0`; `atlas_net` created; `hermes` + `tabs_caddy_1` connected; in-network reachability verified (hermes:9119/api/status → 200, hermes:8642/health → ok).
- [x] Task 0.3 — full Hermes API contract captured to `02_dev_plan/phase0_captures/` (hermes-runs-contract.md, hermes-admin-contract.md, hermes-contract.json). Derived runs API from source to avoid burning the 429-limited quota.
- [x] Task 0.5 — local repo scaffold created at `C:\dev\atlas-control`; plan docs copied; sanitized Phase-0 fixtures copied to `backend/tests/fixtures/`; backend/frontend sanity checks pass; pushed to `https://github.com/brandpreneuragency/atlas` commit `67737fe`. Server clone is pending GitHub deploy-key installation.

## Phase-0 records (CAPTURED — later phases depend on these)
- **Run POST payload:** `POST /v1/runs {"input": "<prompt>"}` → 202 `{"run_id":"run_<hex>","status":"started"}`. (`input` required; may be message-list.)
- **Run terminal event + output field:** SSE field is **`event`** (not `type`); terminal = `run.completed` (also `run.failed`/`run.cancelled`); output text = `output` field; map to internal `output_text`.
- **Run usage fields:** `usage:{input_tokens,output_tokens,total_tokens}` on `run.completed` + on `GET /v1/runs/{id}` when completed.
- **9119 token:** injected as `window.__HERMES_SESSION_TOKEN__="..."`; regex `__HERMES_SESSION_TOKEN__\s*=\s*"([A-Za-z0-9_-]+)"`; header `Authorization: Bearer`; rotates per boot → cache + re-scrape on 401. `/api/status` public.
- **Host-header behavior:** `http://hermes:9119` accepted (200) over atlas_net — NO `Host:` override needed.
- **Subdomain chosen:** `atlas.brandpreneur.net`; DNS check currently returns NXDOMAIN from 1.1.1.1 and VPS resolver, so Caddy append/reload is waiting for propagation/correct record.
- **Caddyfile mount:** `/home/admin/tabs/Caddyfile` → `/etc/caddy/Caddyfile` (Task 0.4 Step 1 verified).

## Decisions / deviations
- 2026-07-06: Derived the runs API contract from `api_server.py` source instead of a live run — the model has an active 429 usage-limit and source is authoritative. No quota spent.
- 2026-07-06: `/api/cron/jobs` returns a **bare JSON array**, not `{"jobs":[]}`. Adapter parses a list.
- 2026-07-06: Only **ONE** Hermes cron job exists now (`App Store Market Scout`, paused, 429). The stale runtime doc's second "Digest Append" job is gone. Phase 6 migration proof targets the single job.
- 2026-07-06: `/api/env` is a **dict keyed by var name** with `{is_set,redacted_value,is_password,category,tools,...}`, not a flat list. Models provider-keys panel renders this shape.
- 2026-07-06: `relaxed_turing` orphan container removed after user approval (`docker rm -f relaxed_turing`).
- 2026-07-06: `make` is not installed in this Windows PowerShell environment; equivalent backend/frontend commands were run directly and passed. Use Git Bash or install make for the literal `make check` gate.

- 2026-07-06: Server clone to `/home/admin/atlas-control` is blocked until the VPS deploy public key is added to GitHub; initial SSH clone failed with `Permission denied (publickey)`.

## DECISION NEEDED
- (none — 0.4 and cleanup are user inputs, not design decisions)
