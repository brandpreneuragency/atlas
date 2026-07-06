FROM node:20-slim AS frontend
WORKDIR /src/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim AS app
WORKDIR /app/backend
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv
COPY backend/ ./
RUN uv sync --frozen --no-dev
COPY --from=frontend /src/frontend/dist /app/static
COPY deploy/backup.sh /app/deploy/backup.sh
RUN chmod +x /app/deploy/backup.sh
# non-root; uid 1000 matches host user `admin` (owner of the mounted ATLAS tree)
RUN useradd --uid 1000 --create-home atlas && chown -R atlas /app/backend
USER atlas
ENV ATLAS_STATIC_DIR=/app/static
EXPOSE 8700
HEALTHCHECK CMD curl -f http://localhost:8700/api/health || exit 1
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8700"]
