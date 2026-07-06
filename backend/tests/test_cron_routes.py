from pathlib import Path

import httpx
import pytest
import respx

CSRF = {"X-Atlas-CSRF": "1"}
ADMIN = "http://hermes:9119"

DASHBOARD_INDEX = (
    Path(__file__).parent / "fixtures" / "dashboard_index.html"
).read_text()

JOB = {
    "id": "ae1df3bdd2c5",
    "name": "App Store Market Scout",
    "prompt": "Scout the app store",
    "schedule": {"kind": "cron", "expr": "*/30 * * * *", "display": "*/30 * * * *"},
    "enabled": False,
    "state": "paused",
    "last_status": "error",
    "last_error": "RuntimeError: HTTP 429: The usage limit has been reached",
    "next_run_at": "2026-07-01T03:30:00+00:00",
}


def _mock_index():
    respx.get(f"{ADMIN}/").mock(
        return_value=httpx.Response(200, text=DASHBOARD_INDEX)
    )


async def _login(client):
    response = await client.post("/api/auth/login", json={"password": "testpw"})
    assert response.status_code == 204


async def _feed_summaries(client):
    rows = (await client.get("/api/events?limit=20")).json()
    return [r["payload"].get("summary") for r in rows]


@pytest.mark.asyncio
@respx.mock
async def test_cron_list_proxies_jobs(app_client):
    _mock_index()
    respx.get(f"{ADMIN}/api/cron/jobs").mock(
        return_value=httpx.Response(200, json=[JOB])
    )
    await _login(app_client)
    response = await app_client.get("/api/hermes/cron")
    assert response.status_code == 200
    jobs = response.json()
    assert jobs[0]["id"] == "ae1df3bdd2c5"
    assert jobs[0]["schedule"]["expr"] == "*/30 * * * *"
    assert jobs[0]["last_error"].endswith("usage limit has been reached")


@pytest.mark.asyncio
@respx.mock
async def test_cron_create_validates_expr(app_client):
    _mock_index()
    await _login(app_client)
    response = await app_client.post(
        "/api/hermes/cron",
        json={
            "name": "Bad",
            "prompt": "x",
            "schedule": {"kind": "cron", "expr": "not a cron"},
        },
        headers=CSRF,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
@respx.mock
async def test_cron_create_proxies_and_events(app_client):
    _mock_index()
    route = respx.post(f"{ADMIN}/api/cron/jobs").mock(
        return_value=httpx.Response(200, json={**JOB, "name": "New Job"})
    )
    await _login(app_client)
    response = await app_client.post(
        "/api/hermes/cron",
        json={
            "name": "New Job",
            "prompt": "do things",
            "schedule": {"kind": "cron", "expr": "*/30 * * * *"},
            "skills": ["scout"],
        },
        headers=CSRF,
    )
    assert response.status_code == 200
    assert route.called
    assert any(
        s == "created cron job 'New Job'" for s in await _feed_summaries(app_client)
    )


@pytest.mark.asyncio
@respx.mock
async def test_cron_update_patches(app_client):
    _mock_index()
    route = respx.put(f"{ADMIN}/api/cron/jobs/ae1df3bdd2c5").mock(
        return_value=httpx.Response(200, json=JOB)
    )
    await _login(app_client)
    response = await app_client.put(
        "/api/hermes/cron/ae1df3bdd2c5",
        json={"schedule": {"kind": "cron", "expr": "0 * * * *"}},
        headers=CSRF,
    )
    assert response.status_code == 200
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_cron_update_rejects_bad_expr(app_client):
    _mock_index()
    await _login(app_client)
    response = await app_client.put(
        "/api/hermes/cron/ae1df3bdd2c5",
        json={"schedule": {"kind": "cron", "expr": "99 99 * * *"}},
        headers=CSRF,
    )
    assert response.status_code == 400


@pytest.mark.parametrize("action", ["pause", "resume", "trigger"])
@pytest.mark.asyncio
@respx.mock
async def test_cron_actions_proxy_and_event(app_client, action):
    _mock_index()
    route = respx.post(f"{ADMIN}/api/cron/jobs/ae1df3bdd2c5/{action}").mock(
        return_value=httpx.Response(200, json=JOB)
    )
    await _login(app_client)
    response = await app_client.post(
        f"/api/hermes/cron/ae1df3bdd2c5/{action}", json={}, headers=CSRF
    )
    assert response.status_code == 200
    assert route.called
    verb = {"pause": "paused", "resume": "resumed", "trigger": "triggered"}[action]
    assert any(
        s == f"{verb} 'App Store Market Scout'"
        for s in await _feed_summaries(app_client)
    )


@pytest.mark.asyncio
@respx.mock
async def test_cron_delete_proxies_and_event(app_client):
    _mock_index()
    respx.get(f"{ADMIN}/api/cron/jobs").mock(
        return_value=httpx.Response(200, json=[JOB])
    )
    route = respx.delete(f"{ADMIN}/api/cron/jobs/ae1df3bdd2c5").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await _login(app_client)
    response = await app_client.request(
        "DELETE", "/api/hermes/cron/ae1df3bdd2c5", headers=CSRF
    )
    assert response.status_code == 204
    assert route.called
    assert any(
        s == "deleted cron job 'App Store Market Scout'"
        for s in await _feed_summaries(app_client)
    )


@pytest.mark.asyncio
@respx.mock
async def test_cron_list_502_when_hermes_down(app_client):
    respx.get(f"{ADMIN}/").mock(side_effect=httpx.ConnectError("boom"))
    await _login(app_client)
    response = await app_client.get("/api/hermes/cron")
    assert response.status_code == 502
