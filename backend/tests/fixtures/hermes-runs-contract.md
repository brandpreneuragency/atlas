# Hermes v0.16.0 — Runs API contract (derived from source, verified 2026-07-06)

Source: `/opt/hermes/gateway/platforms/api_server.py` in container `hermes`. Derived from source rather than a live run to avoid the model's active 429 rate-limit quota. This is authoritative for `HermesClient` (MASTER_PLAN §7) and the `hermes.task` node output mapping (§6).

## POST /v1/runs  (Bearer API_SERVER_KEY)
Request body:
```json
{"input": "<prompt string>"}
```
- `input` is REQUIRED (string, or a list of `{role,content}` message objects — last is the user message, earlier ones become conversation history).
- Optional: `instructions` (system prompt), `previous_response_id`, `conversation_history` (array of `{role,content}`), `session_id`.
- 429 `{"error":{...,"code":"rate_limit_exceeded"}}` when concurrent runs exceed the server max.

Response: **HTTP 202**
```json
{"run_id": "run_<uuid_hex>", "status": "started"}
```
Optional response header `X-Hermes-Session-Key` when a session key header was sent.

## GET /v1/runs/{run_id}  → pollable status
```json
{"object":"hermes.run","run_id":"run_...","status":"...","created_at":<epoch>,"updated_at":<epoch>,"last_event":"...","output":"...","usage":{...},"error":"..."}
```
- Statuses: `started` / `running`, `waiting_for_approval`, `completed`, `failed`, `cancelled`.
- On `completed`: `output` = final text, `usage` = `{input_tokens, output_tokens, total_tokens}`.
- On `failed`: `error` = message.
- 404 `{"error":{...,"code":"run_not_found"}}` if unknown run_id.

## GET /v1/runs/{run_id}/events  → SSE
Lines are `data: {json}\n\n`. Keepalive: `: keepalive\n\n` (every 30s). Terminal comment `: stream closed\n\n`; queue then closes.
Event objects (note the field is **`event`**, not `type`):
```json
{"event":"tool.started","run_id":"...","timestamp":<epoch>,"tool":"<name>","preview":"<str>"}
{"event":"tool.completed","run_id":"...","timestamp":<epoch>,"tool":"<name>","duration":<sec>,"error":<bool>}
{"event":"reasoning.available","run_id":"...","timestamp":<epoch>,"text":"<str>"}
{"event":"approval.request", ...}                      // status → waiting_for_approval
{"event":"run.completed","run_id":"...","timestamp":<epoch>,"output":"<final text>","usage":{"input_tokens":N,"output_tokens":N,"total_tokens":N}}
{"event":"run.failed","run_id":"...","timestamp":<epoch>,"error":"<msg>"}
{"event":"run.cancelled","run_id":"...","timestamp":<epoch>}
```
`run.completed` / `run.failed` / `run.cancelled` are terminal.

## Adapter mapping decisions (record — MASTER_PLAN §6/§7)
- `HermesClient.create_run(prompt)` → `POST {"input": prompt}`; return `run_id`.
- `run_events()` parses `data:` lines to dicts; terminal = `event in {run.completed, run.failed, run.cancelled}`.
- `hermes.task` node output `{output_text, hermes_run_id, usage}`:
  - `output_text` ← run.completed `output` field (API calls it `output`, our internal name stays `output_text`).
  - `usage` ← run.completed `usage` (`input_tokens`/`output_tokens`/`total_tokens`).
- Approval: `approval.request` event → create `approvals(kind="hermes_run")`; resolve via `POST /v1/runs/{id}/approval`.

## /v1/capabilities (features flags to trust)
`run_submission, run_status, run_events_sse, run_stop, run_approval_response, tool_progress_events, approval_events` all `true`. `admin_config_rw:false`, `jobs_admin:false`, `memory_write_api:false`, `cors:false`. Session headers: `X-Hermes-Session-Id`, `X-Hermes-Session-Key`.
