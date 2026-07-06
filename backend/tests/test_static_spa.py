from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest_asyncio.fixture
async def spa_client(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (static / "assets").mkdir()
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    settings = Settings(
        data_dir=tmp_path,
        password="testpw",
        secret_key="s",
        mock_hermes=True,
        dev_mode=True,
        static_dir=static,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            yield client


async def test_spa_fallback_serves_index_html(spa_client) -> None:
    resp = await spa_client.get("/login")
    assert resp.status_code == 200
    assert resp.text == "<html>app</html>"


async def test_spa_fallback_asset_served_as_file(spa_client) -> None:
    resp = await spa_client.get("/assets/app.js")
    assert resp.status_code == 200
    assert resp.text == "console.log(1)"


async def test_spa_fallback_api_paths_not_served(spa_client) -> None:
    # Unknown /api/* paths must NOT be served index.html; auth middleware blocks
    # them (401) for unauthenticated requests.
    resp = await spa_client.get("/api/does-not-exist")
    assert resp.status_code == 401
