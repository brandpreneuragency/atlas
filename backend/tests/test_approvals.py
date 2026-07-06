"""Task 7.2 — approval flow end-to-end (gate notify, timeout expiry,
hermes-side approvals)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text

from app.db import get_session
from app.engine.mock import MockHermes
from app.notify import telegram as telegram_notify

CSRF = {"X-Atlas-CSRF": "1"}


def gate_graph(*, timeout_h: float = 24, notify: list[str] | None = None):
    return {
        "nodes": [
            {"id": "t", "type": "trigger.manual", "position": {"x": 0, "y": 0},
             "config": {}},
            {"id": "g", "type": "gate.approval", "position": {"x": 1, "y": 0},
             "config": {"message": "Publish digest?", "timeout_h": timeout_h,
                        "notify": notify or []}},
            {"id": "ok", "type": "file.op", "position": {"x": 2, "y": 0},
             "config": {"op": "write", "path": "approved.md", "content": "OK"}},
            {"id": "no", "type": "file.op", "position": {"x": 2, "y": 1},
             "config": {"op": "write", "path": "rejected.md", "content": "NO"}},
        ],
        "edges": [
            {"id": "e1", "source": "t", "target": "g", "condition": None},
            {"id": "e2", "source": "g", "target": "ok", "condition": "approved"},
            {"id": "e3", "source": "g", "target": "no", "condition": "rejected"},
        ],
    }


def hermes_graph():
    return {
        "nodes": [
            {"id": "t", "type": "trigger.manual", "position": {"x": 0, "y": 0},
             "config": {}},
            {"id": "h", "type": "hermes.task", "position": {"x": 1, "y": 0},
             "config": {"prompt": "do a thing", "timeout_s": 5, "retries": 0}},
        ],
        "edges": [{"id": "e1", "source": "t", "target": "h", "condition": None}],
    }


async def _create_workflow(client, graph, name="wf"):
    response = await client.post(
        "/api/workflows",
        json={"name": name, "graph": graph},
        headers=CSRF,
    )
    assert response.status_code == 201, response.text
    wf_id = response.json()["id"]
    enable = await client.post(
        f"/api/workflows/{wf_id}/enable", json={"enabled": True}, headers=CSRF
    )
    assert enable.status_code == 200
    return wf_id


async def _run(client, wf_id, payload=None):
    response = await client.post(
        f"/api/workflows/{wf_id}/run",
        json={"dry_run": False, "payload": payload or {}},
        headers=CSRF,
    )
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


async def _wait_run_status(run_id, statuses, timeout=5.0):
    async def _poll():
        while True:
            async with get_session() as session:
                row = (
                    await session.execute(
                        text("SELECT status, error FROM runs WHERE id=:id"),
                        {"id": run_id},
                    )
                ).one()
            if row.status in statuses:
                return row
            await asyncio.sleep(0.01)

    return await asyncio.wait_for(_poll(), timeout)


async def _pending_approvals(client):
    response = await client.get("/api/approvals?status=pending")
    assert response.status_code == 200
    return response.json()


async def test_gate_notify_telegram_sends_message_with_run_link(
    wf_client, monkeypatch
):
    client, app = wf_client
    sent: list[str] = []

    async def fake_send(message: str) -> bool:
        sent.append(message)
        return True

    monkeypatch.setattr(telegram_notify, "send", fake_send)
    wf_id = await _create_workflow(
        client, gate_graph(notify=["telegram"]), name="notify-gate"
    )
    run_id = await _run(client, wf_id)
    await _wait_run_status(run_id, {"waiting_approval"})
    # allow the notify hook to complete
    for _ in range(100):
        if sent:
            break
        await asyncio.sleep(0.01)
    assert sent, "telegram notify was not called on gate parking"
    assert "Publish digest?" in sent[0]
    public_url = app.state.settings.public_url
    assert f"{public_url}/runs/{run_id}" in sent[0]


async def test_gate_without_telegram_in_notify_sends_nothing(wf_client, monkeypatch):
    client, app = wf_client
    sent: list[str] = []

    async def fake_send(message: str) -> bool:
        sent.append(message)
        return True

    monkeypatch.setattr(telegram_notify, "send", fake_send)
    wf_id = await _create_workflow(client, gate_graph(notify=[]), name="quiet-gate")
    run_id = await _run(client, wf_id)
    await _wait_run_status(run_id, {"waiting_approval"})
    await asyncio.sleep(0.05)
    assert sent == []


async def test_resolve_approved_completes_run(wf_client):
    client, app = wf_client
    wf_id = await _create_workflow(client, gate_graph(), name="resolve-ok")
    run_id = await _run(client, wf_id)
    await _wait_run_status(run_id, {"waiting_approval"})
    pending = await _pending_approvals(client)
    assert len(pending) == 1 and pending[0]["run_id"] == run_id
    response = await client.post(
        f"/api/approvals/{pending[0]['id']}/resolve",
        json={"decision": "approved"},
        headers=CSRF,
    )
    assert response.status_code == 200
    row = await _wait_run_status(run_id, {"succeeded", "failed"})
    assert row.status == "succeeded", row.error
    jail = app.state.settings.atlas_root
    assert (jail / "approved.md").exists()
    assert not (jail / "rejected.md").exists()


async def test_resolve_rejected_follows_rejected_edge(wf_client):
    client, app = wf_client
    wf_id = await _create_workflow(client, gate_graph(), name="resolve-no")
    run_id = await _run(client, wf_id)
    await _wait_run_status(run_id, {"waiting_approval"})
    pending = await _pending_approvals(client)
    response = await client.post(
        f"/api/approvals/{pending[0]['id']}/resolve",
        json={"decision": "rejected"},
        headers=CSRF,
    )
    assert response.status_code == 200
    row = await _wait_run_status(run_id, {"succeeded", "failed"})
    assert row.status == "succeeded", row.error
    jail = app.state.settings.atlas_root
    assert (jail / "rejected.md").exists()
    assert not (jail / "approved.md").exists()


async def test_gate_timeout_expires_approval_and_fails_run(wf_client):
    client, app = wf_client
    # 1e-7 h = 0.36 ms — already elapsed by the time we check
    wf_id = await _create_workflow(
        client, gate_graph(timeout_h=0.0000001), name="timeout-gate"
    )
    run_id = await _run(client, wf_id)
    await _wait_run_status(run_id, {"waiting_approval"})
    await asyncio.sleep(0.05)
    await app.state.engine.expire_approvals()
    row = await _wait_run_status(run_id, {"failed"})
    assert row.error == "approval timed out"
    async with get_session() as session:
        approval = (
            await session.execute(
                text("SELECT status FROM approvals WHERE run_id=:id"), {"id": run_id}
            )
        ).one()
    assert approval.status == "expired"


async def test_gate_not_yet_timed_out_is_untouched(wf_client):
    client, app = wf_client
    wf_id = await _create_workflow(client, gate_graph(timeout_h=24), name="fresh-gate")
    run_id = await _run(client, wf_id)
    await _wait_run_status(run_id, {"waiting_approval"})
    await app.state.engine.expire_approvals()
    async with get_session() as session:
        row = (
            await session.execute(
                text("SELECT status FROM runs WHERE id=:id"), {"id": run_id}
            )
        ).one()
    assert row.status == "waiting_approval"


class ApprovalMockHermes(MockHermes):
    """MockHermes whose run emits approval.request, then waits for approve_run."""

    def __init__(self) -> None:
        super().__init__()
        self.approved = asyncio.Event()
        self.approve_calls: list[tuple[str, str, str]] = []

    async def approve_run(self, run_id: str, approval_id: str, decision: str) -> None:
        self.approve_calls.append((run_id, approval_id, decision))
        self.approved.set()

    async def run_events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        yield {"event": "run.started", "run_id": run_id}
        yield {
            "event": "approval.request",
            "run_id": run_id,
            "approval_id": "appr-1",
            "message": "Allow dangerous tool?",
        }
        await asyncio.wait_for(self.approved.wait(), timeout=5)
        yield {
            "event": "run.completed",
            "run_id": run_id,
            "output": "done after approval",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }


async def test_hermes_approval_request_creates_row_and_resolve_calls_approve_run(
    wf_client,
):
    client, app = wf_client
    mock = ApprovalMockHermes()
    app.state.engine._hermes_factory = lambda: mock

    wf_id = await _create_workflow(client, hermes_graph(), name="hermes-appr")
    run_id = await _run(client, wf_id)

    # the approvals row appears while the hermes stream is parked
    async def _poll_pending():
        while True:
            pending = await _pending_approvals(client)
            if pending:
                return pending
            await asyncio.sleep(0.01)

    pending = await asyncio.wait_for(_poll_pending(), timeout=5)
    approval = pending[0]
    assert approval["kind"] == "hermes_run"
    assert approval["external_ref"].startswith("mock-run-")
    assert approval["run_id"] == run_id
    assert "Allow dangerous tool?" in approval["message"]

    response = await client.post(
        f"/api/approvals/{approval['id']}/resolve",
        json={"decision": "approved"},
        headers=CSRF,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    row = await _wait_run_status(run_id, {"succeeded", "failed"})
    assert row.status == "succeeded", row.error
    assert mock.approve_calls == [("mock-run-1", "appr-1", "approved")]
    # step output flowed through after the approval
    async with get_session() as session:
        step = (
            await session.execute(
                text(
                    "SELECT output FROM run_steps WHERE run_id=:id AND node_id='h'"
                ),
                {"id": run_id},
            )
        ).one()
    assert "done after approval" in step.output
    assert json.loads(step.output)["output_text"] == "done after approval"
