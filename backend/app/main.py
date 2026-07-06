from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth import ApiAuthMiddleware, CsrfMiddleware, RateLimiter, bootstrap_password, create_auth_router
from app.config import Settings, get_settings
from app.db import init_db
from app.routers import hermes, system


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db_path = resolved_settings.data_dir / "atlas.db"
        engine = await init_db(db_path)
        await bootstrap_password(resolved_settings)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="ATLAS Control", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(ApiAuthMiddleware)
    app.include_router(create_auth_router(RateLimiter()))
    app.include_router(system.router)
    app.include_router(hermes.router)

    static_dir = resolved_settings.static_dir
    if static_dir is not None and Path(static_dir).exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
