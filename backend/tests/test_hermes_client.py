import json
from pathlib import Path

import httpx
import pytest
import respx

from app.config import Settings
from app.hermes.client import HermesClient
from app.hermes.schemas import HermesUnavailable
from app.main import create_app


def _fixture() -> dict:
    return json.loads(Path("tests/fixtures/hermes-contract.json").read_text())


@pytest.mark.asyncio
@respx.mock
async def test_health_sends_bearer_and_returns_json():
    payload = _fixture()["health_detailed"]
    route = respx.get("http://hermes:8642/health/detailed").mock(
        return_value=httpx.Response(200, json=payload)
    )

    result = await HermesClient("http://hermes:8642", "testkey").health()

    assert result == payload
    assert route.called
    assert route.calls.last.request.headers["Authorization"] == "Bearer testkey"


@pytest.mark.asyncio
@respx.mock
async def test_health_connect_error_raises_unavailable():
    respx.get("http://hermes:8642/health/detailed").mock(
        side_effect=httpx.ConnectError("boom")
    )

    with pytest.raises(HermesUnavailable):
        await HermesClient("http://hermes:8642", "testkey").health()


@pytest.mark.asyncio
@respx.mock
async def test_health_endpoint_degrades_when_hermes_unreachable(tmp_path):
    respx.get("http://hermes:8642/health/detailed").mock(
        side_effect=httpx.ConnectError("boom")
    )
    settings = Settings(
        data_dir=tmp_path,
        password="testpw",
        secret_key="testsecret",
        hermes_api_key="testkey",
        mock_hermes=False,
        dev_mode=True,
        static_dir=None,
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["hermes"]["runs_api"].startswith("unreachable:")
