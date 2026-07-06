import respx
import httpx
import pytest

from app.config import Settings
from app.main import create_app


# ---- GET /api/agents ------------------------------------------------------


async def _login(client) -> None:
    r = await client.post("/api/auth/login", json={"password": "testpw"})
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_agents_returns_seeded_agent_with_live_status(app_client):
    await _login(app_client)
    response = await app_client.get("/api/agents")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 1
    agent = agents[0]
    assert agent["name"] == "Hermes"
    assert agent["kind"] == "hermes"
    assert agent["runs_url"] == "http://hermes:8642"
    assert agent["admin_url"] == "http://hermes:9119"
    assert agent["enabled"] is True
    # live fields merged in (mock adapters)
    assert agent["status"] == "ok"
    assert agent["model"] is not None
    assert agent["active_runs"] == 0


@pytest.mark.asyncio
@respx.mock
async def test_agents_unreachable_does_not_500(tmp_path):
    # real-mode app; health adapter connect-fails → card marked unreachable.
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
            await client.post("/api/auth/login", json={"password": "testpw"})
            response = await client.get("/api/agents")
    assert response.status_code == 200
    agent = response.json()[0]
    assert agent["status"] == "unreachable"
    assert agent["active_runs"] == 0


# ---- GET /api/hermes/sessions --------------------------------------------


@pytest.mark.asyncio
async def test_hermes_sessions_proxies_mock(app_client):
    await _login(app_client)
    response = await app_client.get("/api/hermes/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert isinstance(sessions, list)
    assert sessions and sessions[0]["id"] == "mock-session-1"


@pytest.mark.asyncio
async def test_hermes_sessions_passes_q(app_client):
    await _login(app_client)
    response = await app_client.get("/api/hermes/sessions?q=ping&limit=7")
    assert response.status_code == 200


# ---- POST /api/hermes/chat ------------------------------------------------


@pytest.mark.asyncio
async def test_hermes_chat_streams_and_creates_thread(stream_client):
    # first message → new thread created
    async with stream_client.stream(
        "POST",
        "/api/hermes/chat",
        json={"thread_id": None, "message": "Reply PONG"},
        headers={"X-Atlas-CSRF": "1"},
    ) as response:
        assert response.status_code == 200
        tokens = []
        saw_done = False
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                if line.split(":", 1)[1].strip() == "done":
                    saw_done = True
                    break
                continue
            if line.startswith("data:"):
                tokens.append(line[len("data:"):].strip())
        assert saw_done
        assert "".join(tokens) == "Reply PONG"

    # a chat_threads row must exist; fetch it back via the threads listing API
    threads = await stream_client.get("/api/hermes/threads")
    assert threads.status_code == 200
    body = threads.json()
    assert isinstance(body, list) and len(body) == 1
    thread_id = body[0]["id"]
    # second message reuses the thread (no new row)
    async with stream_client.stream(
        "POST",
        "/api/hermes/chat",
        json={"thread_id": thread_id, "message": "again"},
        headers={"X-Atlas-CSRF": "1"},
    ) as response:
        assert response.status_code == 200
        async for _line in response.aiter_lines():
            if _line.startswith("event:") and _line.split(":", 1)[1].strip() == "done":
                break
    threads2 = await stream_client.get("/api/hermes/threads")
    assert len(threads2.json()) == 1  # still only one thread