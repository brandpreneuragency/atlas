"""Task 7.3 — brain review queue backend."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db import get_session
from app.engine.mock import MockHermes

CSRF = {"X-Atlas-CSRF": "1"}

NOTE = """---
source_path: 01_inbox/01_short/raw-idea.md
category: 01_short
---
A candidate insight about app store pricing.

- [ ] Approved
- [ ] Rejected
"""


def _seed_notes(jail):
    pending = jail / "03_brain" / "01_review" / "pending"
    pending.mkdir(parents=True)
    (pending / "2026-07-06-raw-idea.md").write_text(NOTE, encoding="utf-8")
    (pending / "2026-07-06-second.md").write_text(
        NOTE.replace("raw-idea", "second"), encoding="utf-8"
    )
    return pending


async def test_review_lists_pending_notes(wf_client):
    client, app = wf_client
    _seed_notes(app.state.settings.atlas_root)
    response = await client.get("/api/review")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    names = {item["name"] for item in items}
    assert names == {"2026-07-06-raw-idea.md", "2026-07-06-second.md"}
    first = next(i for i in items if i["name"] == "2026-07-06-raw-idea.md")
    assert first["frontmatter"]["source_path"] == "01_inbox/01_short/raw-idea.md"
    assert first["source_path"] == "01_inbox/01_short/raw-idea.md"
    assert "app store pricing" in first["body_preview"]


async def test_review_empty_when_no_pending_dir(wf_client):
    client, _app = wf_client
    response = await client.get("/api/review")
    assert response.status_code == 200
    assert response.json() == []


class RecordingMock(MockHermes):
    def __init__(self) -> None:
        super().__init__()
        self.prompts: list[str] = []

    async def create_run(self, prompt: str, *, session_key: str | None = None) -> str:
        self.prompts.append(prompt)
        return await super().create_run(prompt, session_key=session_key)


async def test_decide_dispatches_hermes_run(wf_client):
    client, app = wf_client
    _seed_notes(app.state.settings.atlas_root)
    mock = RecordingMock()
    app.state.engine._hermes_factory = lambda: mock

    response = await client.post(
        "/api/review/2026-07-06-raw-idea.md/decide",
        json={"decision": "approved"},
        headers=CSRF,
    )
    assert response.status_code == 200, response.text
    assert response.json()["run_id"] == "mock-run-1"
    prompt = mock.prompts[0]
    assert "03_brain/01_review/pending/2026-07-06-raw-idea.md" in prompt
    assert "Decision: approved" in prompt
    # the note itself is NOT moved by us — Hermes does the moves
    pending = app.state.settings.atlas_root / "03_brain" / "01_review" / "pending"
    assert (pending / "2026-07-06-raw-idea.md").exists()

    async def _wait_event(kind):
        while True:
            async with get_session() as session:
                row = (
                    await session.execute(
                        text("SELECT COUNT(*) FROM events WHERE kind=:k"), {"k": kind}
                    )
                ).scalar_one()
            if row:
                return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_wait_event("review.decided"), timeout=5)
    # run events relayed to the feed
    await asyncio.wait_for(_wait_event("hermes.run_event"), timeout=5)


async def test_decide_rejected_in_prompt(wf_client):
    client, app = wf_client
    _seed_notes(app.state.settings.atlas_root)
    mock = RecordingMock()
    app.state.engine._hermes_factory = lambda: mock
    response = await client.post(
        "/api/review/2026-07-06-second.md/decide",
        json={"decision": "rejected"},
        headers=CSRF,
    )
    assert response.status_code == 200
    assert "Decision: rejected" in mock.prompts[0]


async def test_decide_missing_note_404(wf_client):
    client, app = wf_client
    _seed_notes(app.state.settings.atlas_root)
    response = await client.post(
        "/api/review/nope.md/decide", json={"decision": "approved"}, headers=CSRF
    )
    assert response.status_code == 404


async def test_decide_traversal_name_rejected(wf_client):
    client, app = wf_client
    _seed_notes(app.state.settings.atlas_root)
    response = await client.post(
        "/api/review/..%2f..%2fsecret.md/decide",
        json={"decision": "approved"},
        headers=CSRF,
    )
    assert response.status_code in (400, 404)


async def test_decide_invalid_decision_422(wf_client):
    client, app = wf_client
    _seed_notes(app.state.settings.atlas_root)
    response = await client.post(
        "/api/review/2026-07-06-raw-idea.md/decide",
        json={"decision": "maybe"},
        headers=CSRF,
    )
    assert response.status_code == 422


class ApprovalRequestingMock(RecordingMock):
    """Emits approval.request mid-run, completes after approve_run."""

    def __init__(self) -> None:
        super().__init__()
        import asyncio as _asyncio

        self.approved = _asyncio.Event()
        self.approve_calls: list[tuple[str, str, str]] = []

    async def approve_run(self, run_id, approval_id, decision):
        self.approve_calls.append((run_id, approval_id, decision))
        self.approved.set()

    async def run_events(self, run_id):
        yield {"event": "run.started", "run_id": run_id}
        yield {
            "event": "approval.request",
            "run_id": run_id,
            "approval_id": "appr-9",
            "message": "Move files?",
        }
        await asyncio.wait_for(self.approved.wait(), timeout=5)
        yield {"event": "run.completed", "run_id": run_id, "output": "moved"}


async def test_review_run_approval_request_reaches_inbox(wf_client):
    client, app = wf_client
    _seed_notes(app.state.settings.atlas_root)
    mock = ApprovalRequestingMock()
    app.state.engine._hermes_factory = lambda: mock

    response = await client.post(
        "/api/review/2026-07-06-raw-idea.md/decide",
        json={"decision": "approved"},
        headers=CSRF,
    )
    assert response.status_code == 200

    async def _poll_pending():
        while True:
            rows = (await client.get("/api/approvals?status=pending")).json()
            if rows:
                return rows
            await asyncio.sleep(0.01)

    pending = await asyncio.wait_for(_poll_pending(), timeout=5)
    approval = pending[0]
    assert approval["kind"] == "hermes_run"
    assert approval["run_id"] is None  # not an engine run
    assert "Move files?" in approval["message"]

    resolve = await client.post(
        f"/api/approvals/{approval['id']}/resolve",
        json={"decision": "approved"},
        headers=CSRF,
    )
    assert resolve.status_code == 200
    assert mock.approve_calls == [("mock-run-1", "appr-9", "approved")]
