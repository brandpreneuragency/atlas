from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import Settings
from app.db import get_session
from app.events import append_event

COOKIE_NAME = "atlas_session"
SESSION_MAX_AGE_S = 7 * 24 * 60 * 60

_hasher = PasswordHasher()


class LoginRequest(BaseModel):
    password: str


class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_s: int = 300) -> None:
        self.max_attempts = max_attempts
        self.window_s = window_s
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        attempts = self._attempts[key]
        while attempts and now - attempts[0] > self.window_s:
            attempts.popleft()
        if len(attempts) >= self.max_attempts:
            return False
        attempts.append(now)
        return True

    def record(self, key: str) -> None:
        """Record an occurrence without enforcing the limit."""
        self._attempts[key].append(time.monotonic())

    def blocked(self, key: str) -> bool:
        """Check the limit without recording an attempt."""
        now = time.monotonic()
        attempts = self._attempts[key]
        while attempts and now - attempts[0] > self.window_s:
            attempts.popleft()
        return len(attempts) >= self.max_attempts


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_session_cookie(secret: str) -> str:
    serializer = URLSafeTimedSerializer(secret, salt="atlas-session")
    return serializer.dumps({"sub": "admin"})


def verify_session_cookie(token: str, secret: str) -> dict[str, Any] | None:
    serializer = URLSafeTimedSerializer(secret, salt="atlas-session")
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE_S)
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) and data.get("sub") == "admin" else None


async def bootstrap_password(settings: Settings) -> None:
    if not settings.password:
        raise RuntimeError("ATLAS_PASSWORD is required")
    async with get_session() as session:
        existing = (
            await session.execute(
                text("SELECT value FROM settings WHERE key = 'password_hash'")
            )
        ).scalar_one_or_none()
        if existing is None:
            await session.execute(
                text("INSERT INTO settings(key, value) VALUES ('password_hash', :value)"),
                {"value": hash_password(settings.password)},
            )
            await session.commit()


async def require_session(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    token = request.cookies.get(COOKIE_NAME)
    if token is None or verify_session_cookie(token, settings.secret_key) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return {"sub": "admin"}


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if (
            request.url.path.startswith("/api")
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/api/auth/login"
            and not request.url.path.startswith("/api/hooks/")
            and request.headers.get("X-Atlas-CSRF") != "1"
        ):
            return JSONResponse({"detail": "CSRF header required"}, status_code=403)
        return await call_next(request)


class ApiAuthMiddleware(BaseHTTPMiddleware):
    _public_paths = {"/api/auth/login", "/api/health"}

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path.startswith("/api/hooks/") or path in self._public_paths:
            return await call_next(request)
        if path.startswith("/api"):
            settings: Settings = request.app.state.settings
            token = request.cookies.get(COOKIE_NAME)
            if token is None or verify_session_cookie(token, settings.secret_key) is None:
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


def create_auth_router(
    rate_limiter: RateLimiter, failure_limiter: RateLimiter | None = None
) -> APIRouter:
    router = APIRouter(prefix="/api/auth")
    # lockout after 20 FAILED attempts per hour per IP (PHASE_8 Task 8.4)
    failures = failure_limiter or RateLimiter(max_attempts=20, window_s=3600)

    @router.post("/login", status_code=204)
    async def login(payload: LoginRequest, request: Request, response: Response) -> None:
        client_host = request.client.host if request.client else "unknown"
        if failures.blocked(client_host):
            raise HTTPException(
                status_code=429, detail="Locked out after repeated failures"
            )
        if not rate_limiter.hit(client_host):
            raise HTTPException(status_code=429, detail="Too many login attempts")

        async with get_session() as session:
            password_hash = (
                await session.execute(
                    text("SELECT value FROM settings WHERE key = 'password_hash'")
                )
            ).scalar_one()
            if not verify_password(payload.password, password_hash):
                failures.record(client_host)
                raise HTTPException(status_code=401, detail="Invalid password")

        # append_event persists AND publishes to live SSE subscribers.
        await append_event("system.login", "auth", "Signed in")

        settings: Settings = request.app.state.settings
        response.set_cookie(
            COOKIE_NAME,
            create_session_cookie(settings.secret_key),
            httponly=True,
            secure=not settings.dev_mode,
            samesite="lax",
            max_age=SESSION_MAX_AGE_S,
        )

    @router.post("/logout", status_code=204, dependencies=[Depends(require_session)])
    async def logout(response: Response) -> None:
        response.delete_cookie(COOKIE_NAME)

    return router
