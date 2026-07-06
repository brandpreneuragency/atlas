"""Task 8.4 — security pass (CSRF, cookie flags, lockout, secret leakage)."""

from __future__ import annotations

import time

import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from app.auth import RateLimiter
from app.config import Settings
from app.main import create_app

CSRF = {"X-Atlas-CSRF": "1"}
FAKE_KEY = "FAKE-SECRET-hermes-key-12345"


async def _login(client):
    response = await client.post("/api/auth/login", json={"password": "testpw"})
    assert response.status_code == 204


def _iter_api_routes(app):
    # FastAPI mounts include_router lazily as _IncludedRouter — unwrap those
    for route in app.routes:
        if isinstance(route, APIRoute):
            yield route
        else:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                for sub in inner.routes:
                    if isinstance(sub, APIRoute):
                        yield sub


def _mutating_api_paths(app) -> list[tuple[str, str]]:
    pairs = []
    for route in _iter_api_routes(app):
        if not route.path.startswith("/api"):
            continue
        if route.path == "/api/auth/login" or route.path.startswith("/api/hooks"):
            continue
        for method in route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            path = route.path
            for param in ("{workflow_id}", "{run_id}", "{approval_id}", "{job_id}", "{name}", "{sid}", "{key}", "{id}"):
                path = path.replace(param, "1")
            # any remaining templated segment
            while "{" in path:
                start = path.index("{")
                end = path.index("}", start)
                path = path[:start] + "1" + path[end + 1 :]
            pairs.append((method, path))
    return pairs


async def test_all_mutating_routes_reject_missing_csrf(app_client, tmp_path):
    await _login(app_client)
    # route table read from a throwaway app instance (no lifespan needed);
    # the CSRF middleware short-circuits before routing, so the client app
    # enforces identically for every listed path
    table_app = create_app(
        Settings(data_dir=tmp_path, password="x", secret_key="x", static_dir=None)
    )
    pairs = _mutating_api_paths(table_app)
    assert len(pairs) > 20  # sanity: the route table is really being walked
    for method, path in pairs:
        response = await app_client.request(method, path, json={})
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}"
        assert response.json()["detail"] == "CSRF header required"


@pytest_asyncio.fixture
async def prod_client(tmp_path):
    """App with dev_mode OFF — cookie must carry the Secure flag."""
    settings = Settings(
        data_dir=tmp_path,
        password="testpw",
        secret_key="testsecret",
        mock_hermes=True,
        dev_mode=False,
        static_dir=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            yield client


async def test_session_cookie_flags_prod(prod_client):
    response = await prod_client.post(
        "/api/auth/login", json={"password": "testpw"}
    )
    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=" in cookie


async def test_logout_clears_cookie(app_client):
    await _login(app_client)
    response = await app_client.post("/api/auth/logout", headers=CSRF)
    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert 'atlas_session=""' in cookie or "atlas_session=;" in cookie


async def test_login_rate_limit_active(app_client):
    for _ in range(5):
        await app_client.post("/api/auth/login", json={"password": "wrong"})
    response = await app_client.post("/api/auth/login", json={"password": "wrong"})
    assert response.status_code == 429


def test_failure_lockout_semantics():
    limiter = RateLimiter(max_attempts=20, window_s=3600)
    for _ in range(19):
        limiter.record("ip")
    assert limiter.blocked("ip") is False
    limiter.record("ip")
    assert limiter.blocked("ip") is True
    # entries expire with the window
    limiter._attempts["ip"].clear()
    limiter._attempts["ip"].extend([time.monotonic() - 3700] * 25)
    assert limiter.blocked("ip") is False


async def test_lockout_blocks_even_correct_password(app_client):
    app = app_client._transport.app
    limiter = app.state.login_failure_limiter
    for key in ("testclient", "unknown", "127.0.0.1"):
        for _ in range(20):
            limiter.record(key)
    response = await app_client.post("/api/auth/login", json={"password": "testpw"})
    assert response.status_code == 429
    assert "locked" in response.json()["detail"].lower()


@pytest_asyncio.fixture
async def secret_client(tmp_path):
    """App configured with a recognizable fake hermes key."""
    settings = Settings(
        data_dir=tmp_path,
        password="testpw",
        secret_key="testsecret",
        hermes_api_key=FAKE_KEY,
        mock_hermes=True,
        dev_mode=True,
        static_dir=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            yield client


async def test_no_endpoint_leaks_the_hermes_api_key(secret_client):
    await _login(secret_client)
    # every GET endpoint that returns config-ish data
    for path in (
        "/api/health",
        "/api/me",
        "/api/agents",
        "/api/settings/notifications",
        "/api/settings/limits",
        "/api/settings/backup",
        "/api/killswitch",
        "/api/events?limit=50",
        "/api/workflows",
    ):
        response = await secret_client.get(path)
        assert FAKE_KEY not in response.text, f"{path} leaked the hermes key"


async def test_telegram_token_never_echoed(app_client):
    await _login(app_client)
    token = "FAKE-TG-TOKEN-98765"
    await app_client.put(
        "/api/settings/notifications",
        json={"telegram_bot_token": token, "telegram_chat_id": "1"},
        headers=CSRF,
    )
    for path in ("/api/settings/notifications", "/api/events?limit=50"):
        response = await app_client.get(path)
        assert token not in response.text, f"{path} leaked the telegram token"
