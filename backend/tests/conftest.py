import socket
import threading
import time

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

pytest_plugins = ("pytest_asyncio",)


def _make_settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        password="testpw",
        secret_key="testsecret",
        mock_hermes=True,
        dev_mode=True,
        static_dir=None,
    )


@pytest_asyncio.fixture
async def app_client(tmp_path):
    settings = _make_settings(tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            yield client


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


@pytest_asyncio.fixture
async def stream_client(tmp_path):
    """Real uvicorn server + httpx client for streaming endpoints.

    httpx ``ASGITransport`` buffers the full response (it awaits the ASGI app
    to completion), so it CANNOT stream SSE. For the events SSE stream we spin a
    real uvicorn instance on an ephemeral port and use httpx's normal HTTP
    transport, which streams chunks as they arrive.
    """
    import uvicorn

    settings = _make_settings(tmp_path)
    app = create_app(settings)
    port = _free_port()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        async with AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            login = await client.post("/api/auth/login", json={"password": "testpw"})
            assert login.status_code == 204
            yield client
    finally:
        server.should_exit = True
        thread.join(timeout=10)

@pytest_asyncio.fixture
async def wf_client(tmp_path):
    """Authenticated client + app with a jailed atlas_root (workflow tests)."""
    jail = tmp_path / "atlas"
    jail.mkdir()
    settings = Settings(
        data_dir=tmp_path,
        atlas_root=jail,
        password="testpw",
        secret_key="s",
        mock_hermes=True,
        dev_mode=True,
        static_dir=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            login = await client.post("/api/auth/login", json={"password": "testpw"})
            assert login.status_code == 204
            yield client, app
