"""Task 5.4 — cron/file/webhook/manual triggers + guards."""

import asyncio
import json

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.config import Settings
from app.db import get_session, init_db
from app.engine.guards import Provenance
from app.engine.triggers import TriggerService

CSRF = {"X-Atlas-CSRF": "1"}


def cron_graph(expr="0 7 * * *"):
    return {
        "nodes": [
            {"id": "t", "type": "trigger.cron", "position": {"x": 0, "y": 0},
             "config": {"expr": expr}},
            {"id": "f", "type": "file.op", "position": {"x": 1, "y": 0},
             "config": {"op": "mkdir", "path": "made"}},
        ],
        "edges": [{"id": "e1", "source": "t", "target": "f", "condition": None}],
    }


def file_drop_graph(watch="01_inbox", glob="*.md", stability=0.05):
    return {
        "nodes": [
            {"id": "t", "type": "trigger.file_drop", "position": {"x": 0, "y": 0},
             "config": {"watch_path": watch, "glob": glob, "stability_s": stability}},
            {"id": "f", "type": "file.op", "position": {"x": 1, "y": 0},
             "config": {"op": "mkdir", "path": "made"}},
        ],
        "edges": [{"id": "e1", "source": "t", "target": "f", "condition": None}],
    }


def webhook_graph(secret="s3cret"):
    return {
        "nodes": [
            {"id": "t", "type": "trigger.webhook", "position": {"x": 0, "y": 0},
             "config": {"secret": secret}},
            {"id": "f", "type": "file.op", "position": {"x": 1, "y": 0},
             "config": {"op": "mkdir", "path": "made"}},
        ],
        "edges": [{"id": "e1", "source": "t", "target": "f", "condition": None}],
    }


class FakeEngine:
    def __init__(self):
        self.submits = []

    async def submit(self, workflow_id, trigger_kind, payload, *, dry_run=False):
        self.submits.append((workflow_id, trigger_kind, payload, dry_run))
        return len(self.submits)


@pytest_asyncio.fixture
async def trig_env(tmp_path):
    jail = tmp_path / "atlas"
    jail.mkdir()
    settings = Settings(
        data_dir=tmp_path, atlas_root=jail, password="x", secret_key="x",
        mock_hermes=True, dev_mode=True, static_dir=None,
    )
    db_engine = await init_db(tmp_path / "atlas.db")
    try:
        yield settings, jail
    finally:
        await db_engine.dispose()


async def insert_workflow(graph, *, enabled=1, name="wf"):
    async with get_session() as session:
        result = await session.execute(
            text(
                "INSERT INTO workflows(name, graph, enabled, version, max_runs_per_hour, "
                "created_at, updated_at) VALUES (:n, :g, :e, 1, 100, '2026-01-01', "
                "'2026-01-01') RETURNING id"
            ),
            {"n": name, "g": json.dumps(graph), "e": enabled},
        )
        wf_id = result.scalar_one()
        await session.commit()
    return wf_id


async def wait_for(predicate, timeout=3.0):
    async def _poll():
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout)


# --- cron ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cron_sync_registers_and_removes_jobs(trig_env):
    settings, _ = trig_env
    engine = FakeEngine()
    service = TriggerService(engine, settings)
    wf_id = await insert_workflow(cron_graph())

    await service.sync()
    job = service.scheduler.get_job(f"wf-{wf_id}")
    assert job is not None
    assert job.misfire_grace_time == 300

    async with get_session() as session:
        await session.execute(
            text("UPDATE workflows SET enabled=0 WHERE id=:id"), {"id": wf_id}
        )
        await session.commit()
    await service.sync()
    assert service.scheduler.get_job(f"wf-{wf_id}") is None


@pytest.mark.asyncio
async def test_cron_fire_calls_engine_submit(trig_env):
    settings, _ = trig_env
    engine = FakeEngine()
    service = TriggerService(engine, settings)
    wf_id = await insert_workflow(cron_graph())
    await service.sync()

    await service.fire_cron(wf_id)
    assert engine.submits[0][0] == wf_id
    assert engine.submits[0][1] == "cron"
    assert "fired_at" in engine.submits[0][2]


@pytest.mark.asyncio
async def test_cron_scheduler_uses_settings_timezone(trig_env):
    settings, _ = trig_env
    service = TriggerService(FakeEngine(), settings)
    assert str(service.scheduler.timezone) == settings.tz


# --- file drop ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_drop_fires_after_stability_window(trig_env):
    settings, jail = trig_env
    engine = FakeEngine()
    service = TriggerService(engine, settings)
    await insert_workflow(file_drop_graph())
    await service.sync()

    inbox = jail / "01_inbox"
    inbox.mkdir()
    target = inbox / "note.md"
    target.write_text("v1", encoding="utf-8")
    await service.handle_file_change(str(target))
    assert engine.submits == []  # not yet — stability window pending

    # modify within the window: debounce resets, still no trigger
    target.write_text("v2", encoding="utf-8")
    await service.handle_file_change(str(target))
    assert engine.submits == []

    await wait_for(lambda: len(engine.submits) == 1)
    assert engine.submits[0][1] == "file_drop"
    assert engine.submits[0][2]["file_path"] == "01_inbox/note.md"

    # quiet again — no double fire
    await asyncio.sleep(0.15)
    assert len(engine.submits) == 1


@pytest.mark.asyncio
async def test_file_drop_glob_and_ignore_patterns(trig_env):
    settings, jail = trig_env
    engine = FakeEngine()
    service = TriggerService(engine, settings)
    await insert_workflow(file_drop_graph(glob="*.md"))
    await service.sync()

    inbox = jail / "01_inbox"
    inbox.mkdir()
    for name in ("skip.txt", ".syncthing.note.md", "x.tmp", ".trash-1", "note.md.tmp"):
        p = inbox / name
        p.write_text("x", encoding="utf-8")
        await service.handle_file_change(str(p))
    await asyncio.sleep(0.15)
    assert engine.submits == []


@pytest.mark.asyncio
async def test_file_drop_outside_watch_path_ignored(trig_env):
    settings, jail = trig_env
    engine = FakeEngine()
    service = TriggerService(engine, settings)
    await insert_workflow(file_drop_graph(watch="01_inbox"))
    await service.sync()

    other = jail / "02_other"
    other.mkdir()
    p = other / "note.md"
    p.write_text("x", encoding="utf-8")
    await service.handle_file_change(str(p))
    await asyncio.sleep(0.15)
    assert engine.submits == []


@pytest.mark.asyncio
async def test_provenance_suppresses_engine_written_files(trig_env):
    settings, jail = trig_env
    engine = FakeEngine()
    service = TriggerService(engine, settings)
    await insert_workflow(file_drop_graph())
    await service.sync()

    inbox = jail / "01_inbox"
    inbox.mkdir()
    target = inbox / "generated.md"
    target.write_text("engine output", encoding="utf-8")
    service.provenance.mark(str(target))
    await service.handle_file_change(str(target))
    await asyncio.sleep(0.15)
    assert engine.submits == []


def test_provenance_ttl_expiry():
    prov = Provenance(ttl_s=0.0)
    prov.mark("x")
    assert prov.check("x") is False  # already expired
    prov2 = Provenance(ttl_s=60)
    prov2.mark("y")
    assert prov2.check("y") is True
    assert prov2.check("z") is False


# --- webhook + manual routes ------------------------------------------------------


async def _create_wf(client, graph):
    response = await client.post(
        "/api/workflows", json={"name": "hookwf", "graph": graph}, headers=CSRF
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_webhook_correct_secret_202(wf_client):
    client, app = wf_client
    wf_id = await _create_wf(client, webhook_graph("topsecret"))
    response = await client.post(
        f"/api/hooks/{wf_id}/topsecret", json={"hello": "world"}
    )
    assert response.status_code == 202
    assert "run_id" in response.json()


@pytest.mark.asyncio
async def test_webhook_wrong_secret_404(wf_client):
    client, app = wf_client
    wf_id = await _create_wf(client, webhook_graph("topsecret"))
    response = await client.post(f"/api/hooks/{wf_id}/wrong", json={})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_webhook_kill_switch_409(wf_client):
    client, app = wf_client
    wf_id = await _create_wf(client, webhook_graph("topsecret"))
    async with get_session() as session:
        await session.execute(
            text("INSERT OR REPLACE INTO settings(key, value) VALUES ('global_pause', '1')")
        )
        await session.commit()
    response = await client.post(f"/api/hooks/{wf_id}/topsecret", json={})
    assert response.status_code == 409
    assert response.json()["detail"] == "paused"


@pytest.mark.asyncio
async def test_webhook_rate_limited_429(wf_client):
    client, app = wf_client
    wf_id = await _create_wf(client, webhook_graph("topsecret"))
    codes = []
    for _ in range(12):
        response = await client.post(f"/api/hooks/{wf_id}/topsecret", json={})
        codes.append(response.status_code)
    assert 429 in codes
    assert codes[:10] == [202] * 10


@pytest.mark.asyncio
async def test_manual_run_and_dry_run(wf_client):
    client, app = wf_client
    wf_id = await _create_wf(client, cron_graph())
    response = await client.post(
        f"/api/workflows/{wf_id}/run", json={"dry_run": True}, headers=CSRF
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    async def dry_flag():
        async with get_session() as session:
            row = (await session.execute(
                text("SELECT dry_run FROM runs WHERE id=:id"), {"id": run_id}
            )).one()
        return row.dry_run

    assert await dry_flag() == 1


@pytest.mark.asyncio
async def test_manual_run_paused_409(wf_client):
    client, app = wf_client
    wf_id = await _create_wf(client, cron_graph())
    async with get_session() as session:
        await session.execute(
            text("INSERT OR REPLACE INTO settings(key, value) VALUES ('global_pause', '1')")
        )
        await session.commit()
    response = await client.post(
        f"/api/workflows/{wf_id}/run", json={"dry_run": False}, headers=CSRF
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "paused"
