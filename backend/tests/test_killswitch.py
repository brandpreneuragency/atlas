from pathlib import Path

import httpx
import pytest
import respx

CSRF = {"X-Atlas-CSRF": "1"}
ADMIN = "http://hermes:9119"

DASHBOARD_INDEX = (
    Path(__file__).parent / "fixtures" / "dashboard_index.html"
).read_text()

JOB_ENABLED = {
    "id": "job-enabled",
    "name": "Enabled Job",
    "enabled": True,
    "state": "scheduled",
}
JOB_ALREADY_PAUSED = {
    "id": "job-paused",
    "name": "User Paused Job",
    "enabled": False,
    "state": "paused",
}


def _mock_admin():
    respx.get(f"{ADMIN}/").mock(
        return_value=httpx.Response(200, text=DASHBOARD_INDEX)
    )
    respx.get(f"{ADMIN}/api/cron/jobs").mock(
        return_value=httpx.Response(200, json=[JOB_ENABLED, JOB_ALREADY_PAUSED])
    )


async def _login(client):
    response = await client.post("/api/auth/login", json={"password": "testpw"})
    assert response.status_code == 204


@pytest.mark.asyncio
@respx.mock
async def test_killswitch_pauses_only_enabled_jobs(app_client):
    _mock_admin()
    pause_enabled = respx.post(f"{ADMIN}/api/cron/jobs/job-enabled/pause").mock(
        return_value=httpx.Response(200, json=JOB_ENABLED)
    )
    pause_other = respx.post(f"{ADMIN}/api/cron/jobs/job-paused/pause").mock(
        return_value=httpx.Response(200, json=JOB_ALREADY_PAUSED)
    )
    await _login(app_client)

    response = await app_client.post(
        "/api/killswitch", json={"paused": True}, headers=CSRF
    )
    assert response.status_code == 200
    assert response.json() == {"paused": True}
    assert pause_enabled.call_count == 1
    assert not pause_other.called

    state = await app_client.get("/api/killswitch")
    assert state.json() == {"paused": True}

    rows = (await app_client.get("/api/events?limit=10")).json()
    assert any(r["kind"] == "system.killswitch" for r in rows)


@pytest.mark.asyncio
@respx.mock
async def test_killswitch_resumes_only_what_it_paused(app_client):
    _mock_admin()
    respx.post(f"{ADMIN}/api/cron/jobs/job-enabled/pause").mock(
        return_value=httpx.Response(200, json=JOB_ENABLED)
    )
    resume_enabled = respx.post(f"{ADMIN}/api/cron/jobs/job-enabled/resume").mock(
        return_value=httpx.Response(200, json=JOB_ENABLED)
    )
    resume_other = respx.post(f"{ADMIN}/api/cron/jobs/job-paused/resume").mock(
        return_value=httpx.Response(200, json=JOB_ALREADY_PAUSED)
    )
    await _login(app_client)

    await app_client.post("/api/killswitch", json={"paused": True}, headers=CSRF)
    response = await app_client.post(
        "/api/killswitch", json={"paused": False}, headers=CSRF
    )
    assert response.status_code == 200
    assert resume_enabled.call_count == 1
    assert not resume_other.called  # user-paused job stays paused

    # list cleared: unpausing again resumes nothing
    response = await app_client.post(
        "/api/killswitch", json={"paused": False}, headers=CSRF
    )
    assert response.status_code == 200
    assert resume_enabled.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_killswitch_pause_is_idempotent(app_client):
    _mock_admin()
    pause_route = respx.post(f"{ADMIN}/api/cron/jobs/job-enabled/pause").mock(
        return_value=httpx.Response(200, json=JOB_ENABLED)
    )
    await _login(app_client)

    await app_client.post("/api/killswitch", json={"paused": True}, headers=CSRF)
    response = await app_client.post(
        "/api/killswitch", json={"paused": True}, headers=CSRF
    )
    assert response.status_code == 200
    # second pause is a no-op: already engaged, no double pause calls
    assert pause_route.call_count == 1
