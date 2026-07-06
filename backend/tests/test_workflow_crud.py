"""Task 5.1 — workflow CRUD, graph validation, versioning (PHASE_5.md)."""

import pytest

CSRF = {"X-Atlas-CSRF": "1"}


def example_graph():
    """The MASTER_PLAN §6 example graph (cron → hermes → gate → file.op)."""
    return {
        "nodes": [
            {"id": "n1", "type": "trigger.cron", "position": {"x": 0, "y": 0},
             "config": {"expr": "0 7 * * *"}},
            {"id": "n2", "type": "hermes.task", "position": {"x": 260, "y": 0},
             "config": {"prompt": "Summarize {{trigger.file_path}}", "context_files": [],
                        "session_key": None, "timeout_s": 900, "retries": 1}},
            {"id": "n3", "type": "gate.approval", "position": {"x": 520, "y": 0},
             "config": {"message": "Publish digest?", "timeout_h": 24, "notify": ["telegram"]}},
            {"id": "n4", "type": "file.op", "position": {"x": 780, "y": 0},
             "config": {"op": "write", "path": "04_reports/digest.md",
                        "content": "{{n2.output_text}}"}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2", "condition": None},
            {"id": "e2", "source": "n2", "target": "n3", "condition": None},
            {"id": "e3", "source": "n3", "target": "n4", "condition": "approved"},
        ],
    }


async def _login(client):
    response = await client.post("/api/auth/login", json={"password": "testpw"})
    assert response.status_code == 204


async def _create(client, graph=None, name="wf"):
    return await client.post(
        "/api/workflows",
        json={"name": name, "graph": graph or example_graph()},
        headers=CSRF,
    )


@pytest.mark.asyncio
async def test_create_workflow_returns_201_version_1(app_client):
    await _login(app_client)
    response = await _create(app_client)
    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 1
    assert body["enabled"] is False
    assert body["graph"] == example_graph()

    versions = await app_client.get(f"/api/workflows/{body['id']}/versions")
    assert versions.status_code == 200
    assert [v["version"] for v in versions.json()] == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate,expect_in_error",
    [
        # unknown node type
        (lambda g: g["nodes"][1].update({"type": "hermes.bogus"}), "n2"),
        # edge to missing node
        (lambda g: g["edges"][0].update({"target": "nope"}), "e1"),
        # invalid cron expr
        (lambda g: g["nodes"][0]["config"].update({"expr": "not a cron"}), "n1"),
        # file.op path escaping jail
        (lambda g: g["nodes"][3]["config"].update({"path": "../../etc/passwd"}), "n4"),
    ],
)
async def test_invalid_graph_422_names_offender(app_client, mutate, expect_in_error):
    await _login(app_client)
    graph = example_graph()
    mutate(graph)
    response = await _create(app_client, graph)
    assert response.status_code == 422
    assert expect_in_error in response.json()["detail"]


@pytest.mark.asyncio
async def test_zero_and_two_trigger_nodes_rejected(app_client):
    await _login(app_client)
    graph = example_graph()
    graph["nodes"] = graph["nodes"][1:]  # drop trigger
    graph["edges"] = graph["edges"][1:]
    response = await _create(app_client, graph)
    assert response.status_code == 422
    assert "trigger" in response.json()["detail"]

    graph2 = example_graph()
    graph2["nodes"].append(
        {"id": "t2", "type": "trigger.manual", "position": {"x": 0, "y": 100}, "config": {}}
    )
    response = await _create(app_client, graph2)
    assert response.status_code == 422
    assert "trigger" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_bumps_version_and_snapshots(app_client):
    await _login(app_client)
    created = (await _create(app_client)).json()
    wf_id = created["id"]

    graph2 = example_graph()
    graph2["nodes"][1]["config"]["prompt"] = "Updated prompt"
    response = await app_client.put(
        f"/api/workflows/{wf_id}",
        json={"name": "wf2", "graph": graph2},
        headers=CSRF,
    )
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["name"] == "wf2"

    versions = (await app_client.get(f"/api/workflows/{wf_id}/versions")).json()
    assert [v["version"] for v in versions] == [1, 2]


@pytest.mark.asyncio
async def test_rollback_restores_graph_as_new_version(app_client):
    await _login(app_client)
    created = (await _create(app_client)).json()
    wf_id = created["id"]
    original_graph = created["graph"]

    graph2 = example_graph()
    graph2["nodes"][1]["config"]["prompt"] = "changed"
    await app_client.put(
        f"/api/workflows/{wf_id}", json={"name": "wf", "graph": graph2}, headers=CSRF
    )

    response = await app_client.post(
        f"/api/workflows/{wf_id}/rollback", json={"version": 1}, headers=CSRF
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 3
    assert body["graph"] == original_graph

    missing = await app_client.post(
        f"/api/workflows/{wf_id}/rollback", json={"version": 99}, headers=CSRF
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_enable_disable(app_client):
    await _login(app_client)
    wf_id = (await _create(app_client)).json()["id"]

    on = await app_client.post(
        f"/api/workflows/{wf_id}/enable", json={"enabled": True}, headers=CSRF
    )
    assert on.status_code == 200
    assert on.json()["enabled"] is True

    listing = (await app_client.get("/api/workflows")).json()
    assert listing[0]["enabled"] is True

    off = await app_client.post(
        f"/api/workflows/{wf_id}/enable", json={"enabled": False}, headers=CSRF
    )
    assert off.json()["enabled"] is False


@pytest.mark.asyncio
async def test_delete_cascades(app_client):
    await _login(app_client)
    wf_id = (await _create(app_client)).json()["id"]

    response = await app_client.delete(f"/api/workflows/{wf_id}", headers=CSRF)
    assert response.status_code == 204
    assert (await app_client.get(f"/api/workflows/{wf_id}")).status_code == 404
    versions = await app_client.get(f"/api/workflows/{wf_id}/versions")
    assert versions.status_code in (200, 404)
    if versions.status_code == 200:
        assert versions.json() == []


@pytest.mark.asyncio
async def test_get_missing_workflow_404(app_client):
    await _login(app_client)
    assert (await app_client.get("/api/workflows/9999")).status_code == 404
