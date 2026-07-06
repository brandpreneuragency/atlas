from pathlib import Path

import httpx
import pytest
import respx

CSRF = {"X-Atlas-CSRF": "1"}
ADMIN = "http://hermes:9119"

DASHBOARD_INDEX = (
    Path(__file__).parent / "fixtures" / "dashboard_index.html"
).read_text()

MODEL_INFO = {
    "model": "gpt-5.5",
    "provider": "openai-codex",
    "auto_context_length": 272000,
    "effective_context_length": 272000,
    "capabilities": {"supports_tools": True, "context_window": 1050000},
}
MODEL_OPTIONS = {
    "providers": {
        "openai-codex": ["gpt-5.5", "gpt-5.5-mini"],
        "openrouter": ["stepfun/step-3.7-flash:free"],
    }
}
ENV = {
    "OPENROUTER_API_KEY": {
        "is_set": True,
        "redacted_value": "sk-o...61b8",
        "is_password": True,
        "category": "provider",
        "tools": ["vision_analyze"],
    },
    "NOUS_BASE_URL": {"is_set": False, "redacted_value": None},
}
USAGE = {
    "daily": [
        {
            "day": "2026-06-06",
            "input_tokens": 1067406,
            "output_tokens": 30708,
            "estimated_cost": 0.0,
            "sessions": 47,
        }
    ]
}


def _mock_index():
    respx.get(f"{ADMIN}/").mock(
        return_value=httpx.Response(200, text=DASHBOARD_INDEX)
    )


async def _login(client):
    response = await client.post("/api/auth/login", json={"password": "testpw"})
    assert response.status_code == 204


@pytest.mark.asyncio
@respx.mock
async def test_model_get_merges_info_and_options(app_client):
    _mock_index()
    respx.get(f"{ADMIN}/api/model/info").mock(
        return_value=httpx.Response(200, json=MODEL_INFO)
    )
    respx.get(f"{ADMIN}/api/model/options").mock(
        return_value=httpx.Response(200, json=MODEL_OPTIONS)
    )
    await _login(app_client)
    response = await app_client.get("/api/hermes/model")
    assert response.status_code == 200
    body = response.json()
    assert body["current"]["model"] == "gpt-5.5"
    assert body["current"]["provider"] == "openai-codex"
    assert body["options"]["providers"]["openrouter"] == [
        "stepfun/step-3.7-flash:free"
    ]


@pytest.mark.asyncio
@respx.mock
async def test_model_set_proxies_and_events(app_client):
    _mock_index()
    route = respx.post(f"{ADMIN}/api/model/set").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await _login(app_client)
    response = await app_client.post(
        "/api/hermes/model",
        json={"model": "gpt-5.5-mini", "provider": "openai-codex"},
        headers=CSRF,
    )
    assert response.status_code == 200
    assert route.called
    rows = (await app_client.get("/api/events?limit=10")).json()
    assert any(
        "gpt-5.5-mini" in (r["payload"].get("summary") or "") for r in rows
    )


@pytest.mark.asyncio
@respx.mock
async def test_env_list_stays_masked(app_client):
    _mock_index()
    respx.get(f"{ADMIN}/api/env").mock(return_value=httpx.Response(200, json=ENV))
    await _login(app_client)
    response = await app_client.get("/api/hermes/env")
    assert response.status_code == 200
    body = response.json()
    assert body["OPENROUTER_API_KEY"]["redacted_value"] == "sk-o...61b8"
    # we NEVER unmask: response must not contain any full-key-looking value
    assert "sk-or-v1" not in response.text


@pytest.mark.asyncio
@respx.mock
async def test_env_put_and_delete(app_client):
    _mock_index()
    put_route = respx.put(f"{ADMIN}/api/env").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    del_route = respx.delete(f"{ADMIN}/api/env").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await _login(app_client)

    response = await app_client.put(
        "/api/hermes/env",
        json={"key": "FAKE_PROVIDER_KEY", "value": "fake-value-123"},
        headers=CSRF,
    )
    assert response.status_code == 200
    assert put_route.called

    response = await app_client.request(
        "DELETE", "/api/hermes/env/FAKE_PROVIDER_KEY", headers=CSRF
    )
    assert response.status_code == 200
    assert del_route.called


@pytest.mark.asyncio
@respx.mock
async def test_analytics_proxies(app_client):
    _mock_index()
    respx.get(f"{ADMIN}/api/analytics/usage").mock(
        return_value=httpx.Response(200, json=USAGE)
    )
    respx.get(f"{ADMIN}/api/analytics/models").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    await _login(app_client)
    usage = await app_client.get("/api/hermes/analytics/usage")
    assert usage.status_code == 200
    assert usage.json()["daily"][0]["sessions"] == 47
    models = await app_client.get("/api/hermes/analytics/models")
    assert models.status_code == 200


@pytest.mark.asyncio
@respx.mock
async def test_logs_returns_text(app_client):
    _mock_index()
    respx.get(f"{ADMIN}/api/logs").mock(
        return_value=httpx.Response(200, text="line1\nline2\n")
    )
    await _login(app_client)
    response = await app_client.get("/api/hermes/logs?tail=100")
    assert response.status_code == 200
    assert "line1" in response.text


@pytest.mark.asyncio
async def test_model_prefs_roundtrip(app_client):
    await _login(app_client)
    response = await app_client.get("/api/settings/model-prefs")
    assert response.status_code == 200
    assert response.json() == {"favorites": [], "hidden": []}

    response = await app_client.put(
        "/api/settings/model-prefs",
        json={"favorites": ["gpt-5.5"], "hidden": ["old-model"]},
        headers=CSRF,
    )
    assert response.status_code == 200

    response = await app_client.get("/api/settings/model-prefs")
    assert response.json() == {"favorites": ["gpt-5.5"], "hidden": ["old-model"]}


@pytest.mark.asyncio
async def test_model_prefs_rejects_non_list_members(app_client):
    await _login(app_client)
    response = await app_client.put(
        "/api/settings/model-prefs",
        json={"favorites": "gpt-5.5", "hidden": []},
        headers=CSRF,
    )
    assert response.status_code == 422
    response = await app_client.put(
        "/api/settings/model-prefs",
        json={"favorites": [1, 2], "hidden": []},
        headers=CSRF,
    )
    assert response.status_code == 422
