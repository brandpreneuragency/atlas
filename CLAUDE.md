# Builder Rules

1. TDD is mandatory. Every task: write the failing test → run it, see it fail → implement minimally → run it, see it pass → commit. Never mark a step done without pasting the actual command output into your reasoning.
2. No invention. If a contract (schema, route, signature) is defined here, use it verbatim. If something is genuinely undefined, stop and add a `DECISION NEEDED` line to `docs/PROGRESS.md` instead of guessing.
3. Scope fence. Only touch files listed in the current task. Never refactor unrelated code.
4. Secrets. Never print, log, or commit `API_SERVER_KEY`, password hashes, or `.env` contents. Tests use fake keys.
5. QA gate. At the end of every phase run `make check` (backend: ruff + mypy + pytest; frontend: eslint + tsc --noEmit + vitest + vite build) and fix all failures autonomously before declaring the phase complete.
6. Progress protocol. After each completed task AND at phase end, update `docs/PROGRESS.md` (format in §9). The user resumes sessions with: "Read CLAUDE.md, docs/PROGRESS.md, and docs/MASTER_PLAN.md. Continue with the next phase. Run acceptance criteria when done."
7. Commits. Small, per task, conventional messages (`feat:`, `fix:`, `test:`, `chore:`). Never `--no-verify`.
8. VPS caution. Read-only inspection over SSH is always fine. Mutating server state (docker, Caddy, DNS) happens ONLY in steps that explicitly say so. NEVER restart the `hermes` container unless the phase step explicitly authorizes it (known restart risk: the venv `hermes` entry script is missing on the live container).

## Resume command

Read CLAUDE.md, docs/PROGRESS.md, and docs/MASTER_PLAN.md. Continue with the next phase. Run acceptance criteria when done.

Contracts live in docs/MASTER_PLAN.md §3–§11; never contradict them.

Windows: run `make` targets via Git Bash.
