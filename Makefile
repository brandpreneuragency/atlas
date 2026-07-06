check: check-noexec check-backend check-frontend
# ban dynamic code execution in backend app code (PHASE_5 invariant)
check-noexec: ; @if grep -rnE '(^|[^.A-Za-z0-9_])(eval|exec|compile|__import__)\s*\(' backend/app --include='*.py' | grep -v 'mode="eval"'; then echo 'dynamic execution found in backend/app'; exit 1; else echo 'noexec OK'; fi
check-backend: ; cd backend && uv run ruff check . && uv run mypy app && uv run pytest -q
check-frontend: ; cd frontend && pnpm exec tsc --noEmit && pnpm exec eslint src && pnpm exec vitest run && pnpm build
dev-backend: ; cd backend && uv run uvicorn app.main:app --reload --port 8700
dev-frontend: ; cd frontend && pnpm dev
build: ; docker-compose -f deploy/docker-compose.yml build
deploy: ; ssh admin@142.132.230.137 'cd /home/admin/atlas-control && git pull && docker-compose -f deploy/docker-compose.yml up -d --build'
