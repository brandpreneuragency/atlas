# ATLAS Control — Subagent-Driven Build Playbook

How to execute PHASE_0 → PHASE_8 with a controller session dispatching fresh subagents per task, with two-stage review after every task. This replaces the "paste one prompt card per session" flow — prompt cards remain the fallback for manual/single-session building.

**Core loop:** fresh implementer subagent per task → spec-compliance review → code-quality review → fix loops until both pass → next task. Continuous execution inside a phase; hard stop at phase gates.

---

## 1. Roles and models

| Role | Who | Model tier |
|---|---|---|
| **Controller** | The main Claude Code session. Extracts tasks, curates context, dispatches subagents, answers their questions, runs phase gates, executes VPS-mutating steps itself. Never implements app code directly. | Most capable available (Fable 5 / Opus 4.8) |
| **Implementer** | Fresh subagent per task (`general-purpose`). Codes test-first, self-reviews, commits, reports status. | Per the routing table (§6) — cheap where mechanical, capable where critical |
| **Spec reviewer** | Fresh subagent after each DONE. Reads the actual code, compares to the task spec line by line. Trusts nothing in the report. | Standard (Sonnet 5) |
| **Quality reviewer** | Fresh subagent after spec passes. Reviews the diff (BASE_SHA→HEAD_SHA) for design, tests, maintainability. | Capable (Opus 4.8+) |
| **Phase verifier** | Runs the phase's Acceptance criteria live (curls, browser checks where scriptable). Usually the controller itself. | Controller |

Rules that never bend:

- **One implementer at a time.** Never dispatch implementation subagents in parallel — sequential tasks share files.
- **Two reviews, in order.** Spec compliance first, quality second. Quality review never starts while spec review has open issues. No task is complete while either review has findings.
- **Fix loops are re-reviewed.** Implementer fixes → same reviewer type re-reviews → repeat until ✅.
- **Subagents never read the plan files.** The controller pastes the FULL task text + the relevant MASTER_PLAN sections into the dispatch prompt. (The repo docs exist for humans and for the resume protocol, not as subagent reading assignments.)
- **Secrets:** no subagent prompt ever contains `API_SERVER_KEY`, `ATLAS_PASSWORD`, `ATLAS_SECRET_KEY`, or the Telegram token. Steps that need them run on-server via SSH substitution (as written in the phase files) and are executed by the controller.
- **The `hermes` container is never restarted** by anyone without the user's explicit OK in that session.

## 2. Session and branch strategy

- **One controller session per phase.** A phase (4–6 tasks × implement+review) fits a session comfortably; phases are the natural checkpoint for the human anyway. Session N starts with the kickoff prompt (§3).
- **Branching:** work happens on `phase-N` branches cut from `main`. The phase gate (§5) ends with merge to `main` (no PR needed — solo repo — but `git log --oneline main..phase-N` is reviewed by the controller before merge). `main` is always the last accepted phase. Tag `v0.N` at each merge; `v1.0.0` after Phase 8.
- **Worktrees:** not needed (single sequential builder); plain branches suffice.
- **Context hygiene:** the controller extracts ALL task texts for the phase once at session start, then dispatches from its own notes. If the controller's context runs low mid-phase, finish the current task's review loop, update `docs/PROGRESS.md`, commit, and start a fresh controller session with the kickoff prompt — PROGRESS.md carries the state.

## 3. Controller kickoff prompt (paste to start each phase)

```text
Read CLAUDE.md, docs/PROGRESS.md, docs/MASTER_PLAN.md, and docs/phases/PHASE_<N>.md.
Execute PHASE_<N> using subagent-driven development per docs/EXECUTION_PLAYBOOK.md:
- git checkout -b phase-<N> from main (create if missing)
- Extract every task in the phase with full text; create a todo per task
- For each task in order: dispatch a fresh implementer subagent (model per the
  routing table §6), handle its status, then spec review, then quality review,
  with fix loops until both pass; commit per task; update docs/PROGRESS.md
- Execute VPS/SSH-mutating steps and live verifications yourself — never via
  cheap subagents; never expose secrets in subagent prompts
- Do not pause between tasks. Stop only for: BLOCKED you cannot resolve,
  a DECISION NEEDED, or the phase gate.
- At phase end run the Acceptance criteria + make check, record evidence in
  PROGRESS.md, merge phase-<N> → main, tag v0.<N>, and STOP with a gate report.
```

## 4. The per-task loop (controller procedure)

1. **Prepare context pack** for the task: full task text from the phase file, the MASTER_PLAN sections the task's prompt card names (paste the section text, not the reference), relevant Phase-0 records from PROGRESS.md (payload shapes, token regex), and 1–3 sentences of scene-setting (what exists already, what this enables next).
2. **Dispatch implementer** using the template in §7.1 with the routing-table model. If it asks questions, answer completely (pull answers from MASTER_PLAN/spec; if genuinely undefined, make the call, record it under PROGRESS.md → Decisions) and let it proceed.
3. **Handle status:**
   - `DONE` → proceed to review.
   - `DONE_WITH_CONCERNS` → read concerns; correctness/scope concerns get fixed before review, observations get noted in PROGRESS.md.
   - `NEEDS_CONTEXT` → supply the missing context, re-dispatch same model.
   - `BLOCKED` → diagnose: context problem → re-dispatch with more context; reasoning problem → re-dispatch one tier up; task too big → split it (add the split to PROGRESS.md); plan wrong → DECISION NEEDED, stop and ask the user. Never retry unchanged.
4. **Spec review** (§7.2). Issues → send the SAME task back to a fix subagent with the findings verbatim → re-review. Loop until ✅.
5. **Quality review** (§7.3) with `BASE_SHA` = commit before the task, `HEAD_SHA` = current. Critical/Important issues → fix subagent → re-review. Minor issues → fix now if <5 min, else note in PROGRESS.md.
6. **Close the task:** mark todo complete, update PROGRESS.md (`- [x] Task N.M <name> — commit <sha>`).
7. **Deploy/live-verification steps inside tasks** (e.g., 2.6, 3.4, 4.5, 5.5, 6.5, 7.5): the controller runs these itself, pastes real command output as evidence into PROGRESS.md, and cleans up test artifacts as the step specifies.

## 5. Phase gate (controller, end of every phase)

1. `make check` from clean checkout — green.
2. Run every item in the phase's **Acceptance criteria** literally; paste evidence (command output, URLs checked) into PROGRESS.md.
3. **Dispatch one final whole-phase quality reviewer** (capable model) over `main..phase-N` with the phase goal as requirements — catches cross-task drift the per-task reviews can't see.
4. Fix findings via the loop, re-run `make check`.
5. Update PROGRESS.md (phase done + date + decisions), merge to `main`, tag `v0.N`, push.
6. **STOP.** Report to the user: what shipped, evidence links, open concerns, what Phase N+1 needs from them (e.g., Phase 7 needs the Telegram token; Phase 0 needs subdomain confirmation + orphan-container approval).

## 6. Model routing table

Tiers: **C** = cheap (Haiku 4.5) · **S** = standard (Sonnet 5) · **X** = capable (Opus 4.8 / Fable 5) · **CTRL** = controller runs it directly (VPS mutations, secrets, live verification).

| Phase | Task → tier |
|---|---|
| 0 | 0.1–0.4 **CTRL** (SSH audit, network, captures, Caddy — server state + secrets) · 0.5 scaffold **S** (steps 3–7; controller does GitHub/server clone steps 8–9) |
| 1 | 1.1 **S** · 1.2 auth **S** · 1.3 **S** · 1.4 proxy **S** · 1.5 UI **S** · 1.6 **CTRL** (deploy, server env file) |
| 2 | 2.1 event bus **S** · 2.2 HermesClient **X** (fixture-exact SSE parsing) · 2.3 HermesAdmin **X** (token bootstrap) · 2.4 **S** · 2.5 UI **S** · 2.6 **CTRL** |
| 3 | 3.1 path jail **X** (security boundary) · 3.2 files API **S** · 3.3 UI **S** · 3.4 **CTRL** (incl. live traversal probe) |
| 4 | 4.1 **C** · 4.2 **C** · 4.3 kill switch **S** (resume-only-what-we-paused semantics) · 4.4 UI **S** · 4.5 **CTRL** |
| 5 | 5.1 **S** · 5.2 nodes + expression interpreter **X** · 5.3 engine core **X** · 5.4 triggers **X** (provenance/debounce concurrency) · 5.5 runs API **S**, live smoke **CTRL** |
| 6 | 6.1 canvas **S** · 6.2 config forms **S** · 6.3 run panel **S** · 6.4 **C** · 6.5 **CTRL** |
| 7 | 7.1 transports **C** · 7.2 approval flow **X** (touches engine) · 7.3 review backend **S** · 7.4 UI **C** · 7.5 **CTRL** + user (Telegram creds) |
| 8 | 8.1 backups **CTRL** (host cron) with **S** for the endpoint/UI bits · 8.2 **C** · 8.3 **S** · 8.4 security pass **X** · 8.5 acceptance **CTRL** |

Reviewers: spec **S**, quality **X**, whole-phase **X** — for every phase. When a **C** implementer gets BLOCKED or fails spec review twice on the same task, re-dispatch at **S** (and **S**→**X**) rather than looping.

## 7. Dispatch templates (adapted for this project)

### 7.1 Implementer

```text
Task tool (general-purpose, model per routing table):
description: "Implement Task <N.M>: <name>"
prompt: |
  You are implementing Task <N.M>: <name> for the ATLAS Control project
  (FastAPI + SQLite backend, React+TS+Vite frontend; see Contracts below).

  ## Task Description
  <FULL task text from PHASE_<N>.md, including every checkbox step and code block>

  ## Contracts (binding — never contradict)
  <PASTE the MASTER_PLAN sections named by this task's prompt card, in full>
  <PASTE relevant Phase-0 records from PROGRESS.md, e.g. run payload shape / token regex>

  ## Context
  <1–3 sentences: what already exists, what depends on this task>
  Work from: C:\dev\atlas-control (branch phase-<N>)

  ## Hard rules
  - TDD: write the failing tests specified FIRST, run them and show the failure,
    then implement minimally, then show them passing. Paste real command output.
  - Touch ONLY the files listed in the task. No refactoring outside them.
  - Never print, log, or commit secrets; tests use fake keys.
  - No dynamic code execution (Python's built-in code-string execution functions
    are banned repo-wide; the expression interpreter is an AST-whitelist walker).
  - Run `make check-backend` or `make check-frontend` (whichever applies) and fix
    all lint/type failures before reporting.
  - Commit with the message given in the task.

  ## Before you begin
  If anything in the requirements, approach, or dependencies is unclear — ask now.
  While working, if you hit something unexpected, pause and ask. Never guess.

  ## When you're in over your head
  It is always OK to stop and escalate. Report BLOCKED (can't complete) or
  NEEDS_CONTEXT (missing information) with specifics: what you're stuck on,
  what you tried, what help you need. Bad work is worse than no work.

  ## Before reporting: self-review
  Completeness (every spec item? edge cases?), Quality (clear names, clean code?),
  Discipline (YAGNI — nothing beyond the task?), Testing (tests verify real
  behavior, not mocks-testing-mocks?). Fix what you find, then report.

  ## Report format
  Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
  What you implemented; tests run + results (real output); files changed;
  self-review findings; concerns.
```

### 7.2 Spec-compliance reviewer

```text
Task tool (general-purpose, model S):
description: "Spec review Task <N.M>"
prompt: |
  You are reviewing whether an implementation matches its specification.
  Work from: C:\dev\atlas-control (branch phase-<N>). Diff under review:
  git diff <BASE_SHA>..<HEAD_SHA>

  ## What was requested
  <FULL task text + the same Contracts excerpts given to the implementer>

  ## What the implementer claims
  <implementer's report>

  ## Do not trust the report
  Verify everything by reading the actual code and running the actual tests:
  run `cd backend && uv run pytest -q` (and/or `cd frontend && pnpm exec vitest run`)
  yourself and compare against the claims.

  Check for: missing requirements (spec items skipped, tests specified but absent,
  assertions weakened from the spec); extra work (features/files not in the task);
  misunderstandings (right feature, wrong contract — compare against the Contracts
  text above, e.g. route paths, status codes, schema fields, event kinds).

  Report either:
  ✅ Spec compliant — after code inspection AND green test run
  ❌ Issues — each with file:line and the exact spec text it violates
```

### 7.3 Code-quality reviewer

```text
Task tool (general-purpose, model X):
description: "Quality review Task <N.M>"
prompt: |
  Code review the diff <BASE_SHA>..<HEAD_SHA> in C:\dev\atlas-control.
  Requirements context: Task <N.M> of the ATLAS Control plan (summary: <1–2 lines>).

  Beyond standard review (correctness, tests, error handling, naming):
  - One responsibility per file; units understandable and testable independently?
  - Does it follow the planned file structure; did it bloat any file badly?
  - Security posture where relevant (this project: path jail usage on every fs
    access, no secrets in code/logs, no dynamic code execution, subprocess via
    exec-array not shell strings, CSRF/auth dependencies on new routes)?
  - Async hygiene (no blocking calls in the event loop; timeouts on all external calls)?

  Report: Strengths; Issues as Critical / Important / Minor with file:line;
  Assessment: approve or request changes.
```

## 8. Failure playbook

| Symptom | Action |
|---|---|
| Implementer loops on a failing test | Fix subagent with the exact failing output + one tier up if second loop |
| Spec reviewer and implementer disagree | Controller reads the spec text itself and rules; record the ruling in PROGRESS.md |
| Flaky engine/trigger test | Treat as Critical — the plan bans sleep-based tests; fix determinism, never retry-until-green |
| Live verification fails but tests pass | Controller debugs on the VPS (logs, curls) before dispatching any fix — evidence first, then a fix subagent with the real error |
| Hermes API shape differs from fixtures | Update the fixture from live capture (controller), record in PROGRESS.md Phase-0 records, re-dispatch |
| Two consecutive BLOCKED on same task | Stop. Re-read the plan task; if the plan is wrong, DECISION NEEDED to the user |
| Context low mid-phase | Finish current review loop → PROGRESS.md → commit → fresh controller session with kickoff prompt |

## 9. What the user does

- Approves phase gates (or just reads the gate reports and objects when needed).
- Provides on request: subdomain choice (Phase 0), approval to remove `relaxed_turing` (Phase 0), login password choice (Phase 1), Telegram bot token + chat id (Phase 7), backup folder confirmation (Phase 8).
- Can interrupt any time; the resume command always works:
  *"Read CLAUDE.md, docs/PROGRESS.md, and docs/MASTER_PLAN.md. Continue with the next phase. Run acceptance criteria when done."*
