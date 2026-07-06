# Hermes v0.16.0 — Dashboard (9119) admin contract, verified live 2026-07-06

For `HermesAdmin` (MASTER_PLAN §7). All protected routes require the scraped session token.

## Token scrape (PINNED)
The dashboard injects an ephemeral per-boot token into the index HTML as:
```html
<script>window.__HERMES_SESSION_TOKEN__="<43-char token_urlsafe(32)>";window._...
```
- Extraction regex: `__HERMES_SESSION_TOKEN__\s*=\s*"([A-Za-z0-9_-]+)"`
- Auth header: `Authorization: Bearer <token>`  (verified: 200 on `/api/cron/jobs`).
- Token rotates on every Hermes/dashboard restart → `HermesAdmin._token()` caches it and re-scrapes on 401 (single retry).
- `GET /api/status` is public (no token) — usable as a liveness probe.

## Networking (PINNED)
`http://hermes:9119` over `atlas_net` returns 200 — the DNS-rebinding Host-header middleware ACCEPTS the `hermes:9119` Host. **No `Host:` override needed.** (`hermes:8642` also reachable.)

## GET /api/cron/jobs  → **bare JSON array** (NOT `{"jobs":[...]}`)
Each job:
```json
{"id":"ae1df3bdd2c5","name":"App Store Market Scout",
 "schedule":{"kind":"cron","expr":"*/30 * * * *","display":"*/30 * * * *"},
 "enabled":false,"state":"paused","last_status":"error",
 "last_error":"RuntimeError: HTTP 429: The usage limit has been reached",
 "next_run_at":"2026-07-01T03:30:00+00:00", ...}
```
(Full job objects also carry `prompt`, `skills`, `model`, `provider`, `repeat`, `created_at`, `last_run_at`, `paused_at`, etc. — see jobs.json shape.) CRUD/pause/resume/trigger routes per web_server.py: `POST/PUT/DELETE /api/cron/jobs[/{id}]`, `POST /api/cron/jobs/{id}/{pause|resume|trigger}`.

## GET /api/env  → dict keyed by var name (provider keys, MASKED)
```json
{"OPENROUTER_API_KEY":{"is_set":true,"redacted_value":"sk-o...61b8","description":"...","url":"https://openrouter.ai/keys","category":"provider","is_password":true,"tools":["vision_analyze","mixture_of_agents"],"advanced":false,"channel_managed":false}, "NOUS_BASE_URL":{"is_set":false,"redacted_value":null,...}}
```
- Values are pre-masked by Hermes (`redacted_value`). Our layer NEVER unmasks; no reveal endpoint on our side.
- Write: `PUT /api/env {key,value}`; delete `DELETE /api/env/{key}`.

## GET /api/model/info
```json
{"model":"gpt-5.5","provider":"openai-codex","auto_context_length":272000,"effective_context_length":272000,"capabilities":{"supports_tools":true,"supports_vision":true,"supports_reasoning":true,"context_window":1050000,"max_output_tokens":128000,"model_family":"gpt"}}
```
Also: `GET /api/model/auxiliary`, `POST /api/model/set`.

## GET /api/model/options  (verified live 2026-07-07)
`providers` is an **ARRAY of provider objects**, NOT a name→models record:
```json
{"providers":[{"slug":"nous","name":"Nous Portal","is_current":true,"is_user_defined":false,
  "models":["anthropic/claude-fable-5","openai/gpt-5.5","stepfun/step-3.7-flash:free", "..."],
  "total_models":28,"source":"hermes","pricing":{"...":{}},"free_tier":true,"unavailable_models":["..."]}]}
```
Frontend Models page must map `providers[].models` keyed by `providers[].slug` (this mismatch caused the live "M.map is not a function" crash on /models).

## GET /api/analytics/usage
```json
{"daily":[{"day":"2026-06-06","input_tokens":1067406,"output_tokens":30708,"cache_read_tokens":2218852,"reasoning_tokens":0,"estimated_cost":0.0,"actual_cost":0,"sessions":47,"api_calls":86}, ...]}
```
`actual_cost` is 0 on the current free/codex model. Also `GET /api/analytics/models`.

## Other confirmed routes (web_server.py)
`/api/sessions` (+ `/search`, `/{id}`, `/{id}/messages`, DELETE), `/api/logs?tail=`, `/api/config{,/raw,/schema}`, `/api/providers/oauth*`, `/api/gateway/restart`, `/api/profiles*`, `/api/skills`, websockets `/api/{events,ws,pty,pub}`.

## Deviations from the draft plan (apply during build)
1. Cron endpoint returns a **bare array**, not `{"jobs":[]}` — adapter parses a list.
2. There is currently **only ONE** cron job live (`App Store Market Scout`, paused). The "Digest Append" job from the stale runtime doc is gone. Phase 6 migration proof targets the single existing job.
3. `/api/env` is a **dict keyed by name** with rich metadata, not a flat list — Models page provider-keys panel renders from this shape.
