import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

pytest_plugins = ("pytest_asyncio",)


@pytest_asyncio.fixture
async def app_client(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        password="testpw",
        secret_key="testsecret",
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
