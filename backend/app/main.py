from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import ApiAuthMiddleware, CsrfMiddleware, RateLimiter, bootstrap_password, create_auth_router
from app.config import Settings, get_settings
from app.db import init_db
from app.engine.engine import Engine
from app.engine.triggers import TriggerService
from app.hermes.factory import make_hermes_client
from app.routers import agents, approvals, events, files, hermes, review, system, workflows


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db_path = resolved_settings.data_dir / "atlas.db"
        engine = await init_db(db_path)
        await bootstrap_password(resolved_settings)
        wf_engine = Engine(lambda: make_hermes_client(resolved_settings), resolved_settings)
        await wf_engine.startup()
        triggers = TriggerService(wf_engine, resolved_settings)
        await triggers.sync()
        triggers.start()
        if Path(resolved_settings.atlas_root).exists():
            await triggers.start_watcher()
        app.state.engine = wf_engine
        app.state.triggers = triggers
        try:
            yield
        finally:
            await triggers.stop()
            await wf_engine.shutdown()
            await engine.dispose()

    app = FastAPI(title="ATLAS Control", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(ApiAuthMiddleware)
    login_failures = RateLimiter(max_attempts=20, window_s=3600)
    app.state.login_failure_limiter = login_failures
    app.include_router(create_auth_router(RateLimiter(), login_failures))
    app.include_router(system.router)
    app.include_router(events.router)
    app.include_router(agents.router)
    app.include_router(hermes.router)
    app.include_router(files.router)
    app.include_router(workflows.router)
    app.include_router(workflows.hooks_router)
    app.include_router(approvals.router)
    app.include_router(review.router)

    static_dir = resolved_settings.static_dir
    if static_dir is not None and Path(static_dir).exists():
        index_html = static_dir / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            # SPA fallback: real files under static_dir are served as-is so that
            # assets (/assets/*.js, /favicon.svg, ...) keep working; any other
            # (non-api, non-hermes) path returns index.html for client-side routing.
            if full_path.startswith("api") or full_path.startswith("hermes"):
                raise StarletteHTTPException(status_code=404, detail="Not Found")
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            if index_html.is_file():
                return FileResponse(index_html)
            raise StarletteHTTPException(status_code=404, detail="Not Found")

        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
