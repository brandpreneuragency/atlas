# ATLAS Control — final acceptance run (PHASE_8 Task 8.5, 2026-07-06)

Design spec §6 success criteria executed live against https://atlas.brandpreneur.net.
All API evidence gathered with session-cookie auth over HTTPS — zero SSH needed for
any control action (SSH used only to read verification ground truth).

## 1. Everything from one URL

| Criterion | Result | Evidence |
|---|---|---|
| Observe Hermes live | PASS | `/api/agents` → status ok + current model + active runs; `/api/hermes/sessions` browses live history; Mission Control feed streams SSE (verified Phases 2/4 + this run). |
| One-click pause ALL automation | PASS | `POST /api/killswitch {"paused":true}` → Hermes `jobs.json` shows `enabled: False state: paused`; manual workflow run while engaged → **409** `{"detail":"paused"}`; release restores. (Re-verified live today; jobs.json proof also in Phase 4.5.) |
| Build + run + debug a multi-step workflow with an approval gate | PASS | Phase 6 canvas UI (palette→connect→configure→save, 53 UI tests); live today: gate workflow run 1 parked `waiting_approval` → Inbox approve → run `succeeded`, file written, full event sequence streamed. |
| Manage a Hermes cron job | PASS | Phase 4.5 live: pause/resume/trigger/edit of `App Store Market Scout` with jobs.json proof. |
| Switch model + add a provider key | PASS | Phase 4.5 live: model switched to `deepseek/deepseek-v4-flash` and back (200 + confirmed); `FAKE_TEST_KEY` added/deleted, never unmasked. |
| Browse/edit an ATLAS file | PASS | Phase 3.4 live (tree, read, write 204, stale-mtime 409, traversal 400) + today's write/delete of test artifacts. |
| Approve a brain review note | PASS (today) | Disposable note created via files API → `POST /api/review/acceptance-test-idea.md/decide` → Hermes run `run_ae2fbf5c…`; mid-run `approval.request` appeared in the Inbox (approvals row kind `hermes_run`) → resolved approved → Hermes created the memory note (`02_memory/04_methods/`) + knowledge source note (`03_knowledge/00_sources/`), moved the review note to `approved/` and the raw file to `02_processed/01_short/`. All four artifacts then cleaned up (vault grep = 0). |

## 2. Nothing newly exposed

`ss -tln` on the VPS: 8642, 9119, 8888, 8700 all bound to `127.0.0.1`; public
listeners only 22/80/443. Recorded in docs/SECURITY.md.

## 3. Failure visibility

Workflow with a non-allowlisted `shell.command` run live: `run.failed` appeared
in `/api/events` **670 ms** after submit (<2 s required); run detail shows the
step error `command not in allowlist` one click away.

## 4. Fresh-context resume

This session itself is the proof: it started from the resume command, oriented
from CLAUDE.md + PROGRESS.md + MASTER_PLAN.md alone, detected the actual phase
state, and continued Phases 7–8 with zero extra context.

## Bugs found & fixed during acceptance

- Review-dispatched Hermes runs that raised `approval.request` never reached the
  Inbox (only engine `hermes.task` steps did) → run stuck `waiting_for_approval`
  forever. Fixed in `review/service.py` (+ regression test) — commit 205d690.
- `HermesClient.approve_run` sent `{"approval_id", "decision"}`; the live API
  expects `{"choice": once|session|always|deny}` → every resolve would have
  400'd. Fixed with mapping approved→once, rejected→deny — commit f591d41.

## Known-open items (do not block §6)

- Phase 7.5 Telegram live verification blocked on the user-supplied bot token
  (Settings → Notifications). Transports are unit-tested; the gate notify hook
  is exercised (send returns False + one `system.error` while unconfigured).
- Off-box backup: tarball lands admin-owned in the Syncthing-synced
  `06_backups/`; arrival on the user's PC pending the next Syncthing sync
  (folder allowlisted in `.stignore` today).
