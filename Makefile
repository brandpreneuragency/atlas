check: check-backend check-frontend
check-backend: ; cd backend && uv run ruff check . && uv run mypy app && uv run pytest -q
check-frontend: ; cd frontend && pnpm exec tsc --noEmit && pnpm exec eslint src && pnpm exec vitest run && pnpm build
dev-backend: ; cd backend && uv run uvicorn app.main:app --reload --port 8700
dev-frontend: ; cd frontend && pnpm dev
