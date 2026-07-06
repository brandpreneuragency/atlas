"""Task 5.5 — runs API + cancel + approvals resolution."""

import asyncio

import pytest

from app.db import get_session
from tests.test_triggers import CSRF  # noqa: F401

from sqlalchemy import text


def approval_graph():
    return {
        "nodes": [
            {"id": "t", "type": "trigger.manual", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "g", "type": "gate.approval", "position": {"x": 1, "y": 0},
             "config": {"message": "Go?", "timeout_h": 24, "notify": []}},
            {"id": "f", "type": "file.op", "position": {"x": 2, "y": 0},
             "config": {"op": "mkdir", "path": "done"}},
        ],
        "edges": [
            {"id": "e1", "source": "t", "target": "g", "condition": None},
            {"id": "e2", "source": "g", "target": "f", "condition": "approved"},
        ],
    }


def linear_graph():
    return {
        "nodes": [
            {"id": "t", "type": "trigger.manual", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "f", "type": "file.op", "position": {"x": 1, "y": 0},
             "config": {"op": "write", "path": "r.md", "content": "hello"}},
        ],
        "edges": [{"id": "e1", "source": "t", "target": "f", "condition": None}],
    }


async def _create_wf(client, graph, name="wf"):
    response = await client.post(
        "/api/workflows", json={"name": name, "graph": graph}, headers=CSRF
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _run(client, wf_id, dry_run=False):
    response = await client.post(
        f"/api/workflows/{wf_id}/run", json={"dry_run": dry_run}, headers=CSRF
    )
    assert response.status_code == 200
    return response.json()["run_id"]


async def _wait_run_status(client, run_id, statuses, timeout=5.0):
    async def _poll():
        while True:
            response = await client.get(f"/api/runs/{run_id}")
            body = response.json()
            if body["status"] in statuses:
                return body
            await asyncio.sleep(0.02)

    return await asyncio.wait_for(_poll(), timeout)


@pytest.mark.asyncio
async def test_list_runs_with_filters(wf_client):
    client, app = wf_client
    wf1 = await _create_wf(client, linear_graph(), "one")
    wf2 = await _create_wf(client, linear_graph(), "two")
    r1 = await _run(client, wf1)
    r2 = await _run(client, wf2)
    await _wait_run_status(client, r1, {"succeeded"})
    await _wait_run_status(client, r2, {"succeeded"})

    all_runs = (await client.get("/api/runs")).json()
    assert {r["id"] for r in all_runs} >= {r1, r2}

    filtered = (await client.get(f"/api/runs?workflow_id={wf1}")).json()
    assert [r["id"] for r in filtered] == [r1]

    by_status = (await client.get("/api/runs?status=succeeded&limit=1")).json()
    assert len(by_status) == 1
    assert by_status[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_run_detail_includes_ordered_steps(wf_client):
    client, app = wf_client
    wf_id = await _create_wf(client, linear_graph())
    run_id = await _run(client, wf_id)
    body = await _wait_run_status(client, run_id, {"succeeded"})
    steps = body["steps"]
    assert [s["node_id"] for s in steps] == ["f"]
    assert steps[0]["status"] == "succeeded"
    assert steps[0]["input"]["op"] == "write"
    assert steps[0]["output"]["path"] == "r.md"
    assert steps[0]["error"] is None


@pytest.mark.asyncio
async def test_cancel_waiting_run(wf_client):
    client, app = wf_client
    wf_id = await _create_wf(client, approval_graph())
    run_id = await _run(client, wf_id)
    await _wait_run_status(client, run_id, {"waiting_approval"})

    response = await client.post(f"/api/runs/{run_id}/cancel", headers=CSRF)
    assert response.status_code == 204
    body = await _wait_run_status(client, run_id, {"cancelled"})
    assert body["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_running_stops_active_hermes_run(tmp_path):
    from app.config import Settings
    from app.db import init_db
    from app.engine.engine import Engine
    from app.engine.mock import MockHermes
    from tests.test_engine import make_workflow, wait_status

    jail = tmp_path / "atlas"
    jail.mkdir()
    settings = Settings(
        data_dir=tmp_path, atlas_root=jail, password="x", secret_key="x",
        mock_hermes=True, dev_mode=True, static_dir=None,
    )
    db_engine = await init_db(tmp_path / "atlas.db")
    try:
        stopped = []

        class SlowHermes(MockHermes):
            async def run_events(self, run_id):
                await asyncio.sleep(30)
                yield {}

            async def stop_run(self, run_id):
                stopped.append(run_id)

        engine = Engine(lambda: SlowHermes(), settings)
        wf_id = await make_workflow({
            "nodes": [
                {"id": "t", "type": "trigger.manual", "position": {"x": 0, "y": 0},
                 "config": {}},
                {"id": "h", "type": "hermes.task", "position": {"x": 1, "y": 0},
                 "config": {"prompt": "p", "timeout_s": 60, "retries": 0}},
            ],
            "edges": [{"id": "e1", "source": "t", "target": "h", "condition": None}],
        })
        run_id = await engine.submit(wf_id, "manual", {})
        # wait until the hermes run is registered as active
        for _ in range(200):
            if run_id in engine._active_hermes:
                break
            await asyncio.sleep(0.01)
        assert run_id in engine._active_hermes

        await engine.cancel(run_id)
        assert stopped == ["mock-run-1"]
        row = await wait_status(run_id, {"cancelled"})
        assert row.status == "cancelled"
    finally:
        await db_engine.dispose()


@pytest.mark.asyncio
async def test_approvals_list_and_resolve(wf_client):
    client, app = wf_client
    wf_id = await _create_wf(client, approval_graph())
    run_id = await _run(client, wf_id)
    await _wait_run_status(client, run_id, {"waiting_approval"})

    pending = (await client.get("/api/approvals?status=pending")).json()
    assert len(pending) == 1
    approval_id = pending[0]["id"]
    assert pending[0]["message"] == "Go?"

    response = await client.post(
        f"/api/approvals/{approval_id}/resolve",
        json={"decision": "approved"}, headers=CSRF,
    )
    assert response.status_code == 200
    body = await _wait_run_status(client, run_id, {"succeeded"})
    assert body["status"] == "succeeded"

    async with get_session() as session:
        row = (await session.execute(
            text("SELECT status FROM approvals WHERE id=:id"), {"id": approval_id}
        )).one()
    assert row.status == "approved"
