import asyncio
import json

import pytest

from app.events import append_event, broadcaster


async def _login(client) -> None:
    response = await client.post("/api/auth/login", json={"password": "testpw"})
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_append_event_persists_and_broadcasts(app_client):
    queue = broadcaster.subscribe()
    try:
        event = await append_event(
            "system.error",
            "test",
            "Something broke",
            detail="boom",
        )

        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received["kind"] == "system.error"
        assert received["source"] == "test"
        assert received["payload"]["summary"] == "Something broke"
        assert received["payload"]["detail"] == "boom"
        assert received["id"] == event["id"]

        await _login(app_client)
        response = await app_client.get("/api/events")
        assert response.status_code == 200
        rows = response.json()
        matching = [r for r in rows if r["id"] == event["id"]]
        assert matching, "persisted event must be returned by /api/events"
        row = matching[0]
        assert row["kind"] == "system.error"
        assert row["payload"]["summary"] == "Something broke"
    finally:
        broadcaster.unsubscribe(queue)


@pytest.mark.asyncio
async def test_login_event_is_broadcast_live(app_client):
    # Acceptance: the live feed shows system.login within 2s of logging in,
    # so the login handler must go through append_event (persist + publish).
    queue = broadcaster.subscribe()
    try:
        await _login(app_client)
        received = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert received["kind"] == "system.login"
        assert received["source"] == "auth"
    finally:
        broadcaster.unsubscribe(queue)


@pytest.mark.asyncio
async def test_events_list_pagination(app_client):
    await _login(app_client)

    ids: list[int] = []
    for i in range(30):
        ev = await append_event("run.step_finished", "test", f"step {i}", index=i)
        ids.append(ev["id"])
    # newest first = last inserted at top
    first = await app_client.get("/api/events?limit=10")
    assert first.status_code == 200
    page1 = first.json()
    assert len(page1) == 10
    assert [r["id"] for r in page1] == list(reversed(ids))[:10]

    before_id = page1[-1]["id"]
    second = await app_client.get(f"/api/events?limit=10&before_id={before_id}")
    assert second.status_code == 200
    page2 = second.json()
    assert len(page2) == 10
    # next page must be strictly older ids
    assert all(r["id"] < before_id for r in page2)
    # no overlap between pages
    page1_ids = {r["id"] for r in page1}
    assert all(r["id"] not in page1_ids for r in page2)

    # kind filter narrows result set
    kind_resp = await app_client.get("/api/events?limit=5&kind=system.error")
    assert kind_resp.status_code == 200
    for r in kind_resp.json():
        assert r["kind"] == "system.error"


@pytest.mark.asyncio
async def test_sse_stream_delivers(stream_client):
    # stream_client logs in itself (see conftest); queue already warm.
    async with stream_client.stream("GET", "/api/events/stream") as response:
        assert response.status_code == 200
        # the eager subscription in the route handler ran before the stream
        # headers were sent; small grace so the server task pulls the generator.
        await asyncio.sleep(0.15)
        await append_event("system.error", "test", "boom", code=42)

        parsed: dict | None = None
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                parsed = json.loads(line[len("data:"):].strip())
                break
            if line.startswith(":"):
                # heartbeat comment — keep waiting for a real event
                continue

        assert parsed is not None
        assert parsed["kind"] == "system.error"
        assert parsed["payload"]["summary"] == "boom"
        assert parsed["payload"]["code"] == 42