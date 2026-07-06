check: check-backend check-frontend
check-backend: ; cd backend && uv run ruff check . && uv run mypy app && uv run pytest -q
check-frontend: ; cd frontend && pnpm exec tsc --noEmit && pnpm exec eslint src && pnpm exec vitest run && pnpm build
dev-backend: ; cd backend && uv run uvicorn app.main:app --reload --port 8700
dev-frontend: ; cd frontend && pnpm dev
build: ; docker-compose -f deploy/docker-compose.yml build
deploy: ; ssh admin@142.132.230.137 'cd /home/admin/atlas-control && git pull && docker-compose -f deploy/docker-compose.yml up -d --build'
