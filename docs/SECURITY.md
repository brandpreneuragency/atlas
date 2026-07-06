# ATLAS Control — security pass (PHASE_8 Task 8.4, 2026-07-06)

Automated assertions live in `backend/tests/test_security.py`; manual checks
recorded here with evidence.

## Checklist

| Check | Status | Evidence |
|---|---|---|
| All mutating `/api` routes reject a missing `X-Atlas-CSRF` header | PASS (tested) | `test_all_mutating_routes_reject_missing_csrf` walks the full route table (POST/PUT/PATCH/DELETE, ~30 routes) → every one returns 403. Exemptions by design: `POST /api/auth/login` (no session yet), `/api/hooks/*` (secret-authenticated webhooks). |
| Session cookie HttpOnly + Secure (prod) + SameSite=Lax + expiry | PASS (tested) | `test_session_cookie_flags_prod` (dev_mode off → `Secure` present, `HttpOnly`, `SameSite=lax`, `Max-Age=604800`). |
| Logout invalidates | PASS with caveat | `test_logout_clears_cookie` — cookie deleted. Caveat: sessions are stateless signed tokens (itsdangerous, 7-day max age); a stolen token remains valid until expiry — no server-side revocation list. Accepted for the single-user threat model; rotating `ATLAS_SECRET_KEY` revokes everything. |
| Login rate limit + lockout | PASS (tested) | 5 attempts / 5 min / IP (`test_login_rate_limit_active`) plus lockout after 20 failures/hour/IP that blocks even the correct password (`test_lockout_blocks_even_correct_password`). Limits are in-memory — reset on container restart (acceptable). |
| No secret returned by any endpoint | PASS (tested) | `test_no_endpoint_leaks_the_hermes_api_key` (fake `ATLAS_HERMES_API_KEY` grepped across every config-ish GET), `test_telegram_token_never_echoed` (notifications GET returns only `*_set` booleans), `/api/hermes/env` returns Hermes-masked values untouched with **no reveal endpoint** (Phase 4 decision). |
| No `docker.sock` mount | PASS (manual) | `deploy/docker-compose.yml` mounts only `atlas_control_data:/data`, `/home/admin/atlas:/opt/atlas`, and the env file read-only. |
| Container non-root + hardened | PASS | Dockerfile `USER atlas` (uid 1000 = host `admin`, so files written into the ATLAS mount are owned by the Syncthing user, not root); compose `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`. |
| 8642/9119/8888/8700 loopback only | PASS (manual, 2026-07-06) | `ss -tln` on the VPS: all four bound to `127.0.0.1`; public listeners are only 22 (SSH) and 80/443 (Caddy). App reachable solely via Caddy → `atlas_net`. |
| `shell.command` allowlist empty by default | PASS | The `shell_allowlist` settings key is unset by default → engine resolves it to `[]` → every `shell.command` node fails with `command not in allowlist`. Enabling it is opt-in and sharp: an allowlisted prefix (e.g. `git `) permits ANY arguments to that binary, executed inside the ATLAS jail as the app user. Add prefixes only for read-only commands you fully trust. |

## Notes

- Path traversal defenses (`files/safe_path.py`) carry their own adversarial
  test suite from Phase 3 (null bytes, encoded `..`, symlink escapes).
- Dynamic code execution is banned repo-wide (`make check-noexec` grep gate +
  the AST-whitelist expression interpreter from Phase 5).
- Webhook triggers rate-limit at 10/min/workflow and 404 on secret mismatch.
