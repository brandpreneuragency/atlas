"""Workflow CRUD + versioning routes (MASTER_PLAN §5, PHASE_5 Task 5.1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from app.auth import require_session
from app.db import get_session
from app.engine.engine import EnginePaused
from app.engine.schemas import Graph, validate_graph

router = APIRouter(prefix="/api", dependencies=[Depends(require_session)])
hooks_router = APIRouter(prefix="/api")  # webhook triggers: secret-authed, no session


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    graph: dict[str, Any]
    # None/omitted → global defaults from /api/settings/limits (Task 8.2)
    max_runs_per_hour: int | None = None
    budget_usd_per_run: float | None = None


class EnableIn(BaseModel):
    enabled: bool


class RollbackIn(BaseModel):
    version: int


class RunIn(BaseModel):
    dry_run: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


def _parse_and_validate(graph_dict: dict[str, Any]) -> Graph:
    try:
        graph = Graph.model_validate(graph_dict)
    except ValidationError as exc:
        raise HTTPException(422, detail=f"malformed graph: {exc.errors()[0]['msg']}") from exc
    errors = validate_graph(graph)
    if errors:
        raise HTTPException(422, detail="; ".join(errors))
    return graph


def _row_to_workflow(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "graph": json.loads(row.graph),
        "enabled": bool(row.enabled),
        "version": row.version,
        "max_runs_per_hour": row.max_runs_per_hour,
        "budget_usd_per_run": row.budget_usd_per_run,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


_WF_COLS = (
    "id, name, description, graph, enabled, version, "
    "max_runs_per_hour, budget_usd_per_run, created_at, updated_at"
)


async def _fetch_workflow(session: Any, workflow_id: int) -> Any:
    result = await session.execute(
        text(f"SELECT {_WF_COLS} FROM workflows WHERE id = :id"), {"id": workflow_id}
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(404, detail="workflow not found")
    return row


async def _snapshot_version(
    session: Any, workflow_id: int, version: int, graph_json: str
) -> None:
    await session.execute(
        text(
            "INSERT INTO workflow_versions(workflow_id, version, graph, created_at) "
            "VALUES (:wf, :v, :graph, :ts)"
        ),
        {"wf": workflow_id, "v": version, "graph": graph_json, "ts": _now_iso()},
    )


async def _resync_triggers(request: Request) -> None:
    # cron jobs / file watches must follow enable/update/delete immediately
    triggers = getattr(request.app.state, "triggers", None)
    if triggers is not None:
        await triggers.sync()


@router.get("/workflows")
async def list_workflows() -> list[dict[str, Any]]:
    async with get_session() as session:
        result = await session.execute(
            text(f"SELECT {_WF_COLS} FROM workflows ORDER BY id")
        )
        return [_row_to_workflow(row) for row in result.all()]


@router.post("/workflows", status_code=201)
async def create_workflow(body: WorkflowIn) -> dict[str, Any]:
    from app.routers.system import get_default_limits

    _parse_and_validate(body.graph)
    graph_json = json.dumps(body.graph, separators=(",", ":"))
    now = _now_iso()
    default_mrph, default_budget = await get_default_limits()
    mrph = body.max_runs_per_hour if body.max_runs_per_hour is not None else default_mrph
    budget = (
        body.budget_usd_per_run
        if "budget_usd_per_run" in body.model_fields_set
        else default_budget
    )
    async with get_session() as session:
        result = await session.execute(
            text(
                "INSERT INTO workflows(name, description, graph, enabled, version, "
                "max_runs_per_hour, budget_usd_per_run, created_at, updated_at) "
                "VALUES (:name, :desc, :graph, 0, 1, :mrph, :budget, :now, :now) "
                "RETURNING id"
            ),
            {
                "name": body.name,
                "desc": body.description,
                "graph": graph_json,
                "mrph": mrph,
                "budget": budget,
                "now": now,
            },
        )
        wf_id = result.scalar_one()
        await _snapshot_version(session, wf_id, 1, graph_json)
        await session.commit()
        row = await _fetch_workflow(session, wf_id)
        return _row_to_workflow(row)


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: int) -> dict[str, Any]:
    async with get_session() as session:
        return _row_to_workflow(await _fetch_workflow(session, workflow_id))


@router.put("/workflows/{workflow_id}")
async def update_workflow(workflow_id: int, body: WorkflowIn, request: Request) -> dict[str, Any]:
    _parse_and_validate(body.graph)
    graph_json = json.dumps(body.graph, separators=(",", ":"))
    async with get_session() as session:
        row = await _fetch_workflow(session, workflow_id)
        new_version = row.version + 1
        # omitted limits keep their current values (defaults only apply at create)
        mrph = (
            body.max_runs_per_hour
            if body.max_runs_per_hour is not None
            else row.max_runs_per_hour
        )
        budget = (
            body.budget_usd_per_run
            if "budget_usd_per_run" in body.model_fields_set
            else row.budget_usd_per_run
        )
        await session.execute(
            text(
                "UPDATE workflows SET name=:name, description=:desc, graph=:graph, "
                "version=:v, max_runs_per_hour=:mrph, budget_usd_per_run=:budget, "
                "updated_at=:now WHERE id=:id"
            ),
            {
                "name": body.name,
                "desc": body.description,
                "graph": graph_json,
                "v": new_version,
                "mrph": mrph,
                "budget": budget,
                "now": _now_iso(),
                "id": workflow_id,
            },
        )
        await _snapshot_version(session, workflow_id, new_version, graph_json)
        await session.commit()
        row = _row_to_workflow(await _fetch_workflow(session, workflow_id))
    await _resync_triggers(request)
    return row


@router.delete("/workflows/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: int, request: Request) -> None:
    async with get_session() as session:
        await _fetch_workflow(session, workflow_id)
        await session.execute(
            text("DELETE FROM workflows WHERE id=:id"), {"id": workflow_id}
        )
        await session.commit()
    await _resync_triggers(request)


@router.post("/workflows/{workflow_id}/enable")
async def enable_workflow(workflow_id: int, body: EnableIn, request: Request) -> dict[str, Any]:
    async with get_session() as session:
        await _fetch_workflow(session, workflow_id)
        await session.execute(
            text("UPDATE workflows SET enabled=:e, updated_at=:now WHERE id=:id"),
            {"e": int(body.enabled), "now": _now_iso(), "id": workflow_id},
        )
        await session.commit()
        row = _row_to_workflow(await _fetch_workflow(session, workflow_id))
    await _resync_triggers(request)
    return row


@router.get("/workflows/{workflow_id}/versions")
async def list_versions(workflow_id: int) -> list[dict[str, Any]]:
    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT id, workflow_id, version, created_at FROM workflow_versions "
                "WHERE workflow_id=:wf ORDER BY version"
            ),
            {"wf": workflow_id},
        )
        return [
            {
                "id": row.id,
                "workflow_id": row.workflow_id,
                "version": row.version,
                "created_at": row.created_at,
            }
            for row in result.all()
        ]


@router.post("/workflows/{workflow_id}/rollback")
async def rollback_workflow(workflow_id: int, body: RollbackIn, request: Request) -> dict[str, Any]:
    async with get_session() as session:
        row = await _fetch_workflow(session, workflow_id)
        result = await session.execute(
            text(
                "SELECT graph FROM workflow_versions WHERE workflow_id=:wf AND version=:v"
            ),
            {"wf": workflow_id, "v": body.version},
        )
        target = result.one_or_none()
        if target is None:
            raise HTTPException(404, detail=f"version {body.version} not found")
        new_version = row.version + 1
        await session.execute(
            text(
                "UPDATE workflows SET graph=:graph, version=:v, updated_at=:now WHERE id=:id"
            ),
            {"graph": target.graph, "v": new_version, "now": _now_iso(), "id": workflow_id},
        )
        await _snapshot_version(session, workflow_id, new_version, target.graph)
        await session.commit()
        row = _row_to_workflow(await _fetch_workflow(session, workflow_id))
    await _resync_triggers(request)
    return row


@router.post("/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: int, body: RunIn, request: Request) -> dict[str, Any]:
    async with get_session() as session:
        await _fetch_workflow(session, workflow_id)
    engine = request.app.state.engine
    try:
        run_id = await engine.submit(
            workflow_id, "manual", body.payload, dry_run=body.dry_run
        )
    except EnginePaused:
        raise HTTPException(409, detail="paused") from None
    return {"run_id": run_id}


@hooks_router.post("/hooks/{workflow_id}/{secret}", status_code=202)
async def webhook_trigger(workflow_id: int, secret: str, request: Request) -> dict[str, Any]:
    async with get_session() as session:
        result = await session.execute(
            text("SELECT graph FROM workflows WHERE id=:id"), {"id": workflow_id}
        )
        row = result.one_or_none()
    if row is None:
        raise HTTPException(404, detail="not found")
    expected = None
    for node in json.loads(row.graph).get("nodes", []):
        if node.get("type") == "trigger.webhook":
            expected = node.get("config", {}).get("secret")
            break
    if expected is None or secret != expected:
        raise HTTPException(404, detail="not found")

    triggers = request.app.state.triggers
    if not triggers.hook_limiter.allow(workflow_id):
        raise HTTPException(429, detail="rate limited")

    try:
        body = await request.json()
    except Exception:
        body = {}
    engine = request.app.state.engine
    try:
        run_id = await engine.submit(workflow_id, "webhook", {"body": body})
    except EnginePaused:
        raise HTTPException(409, detail="paused") from None
    return {"run_id": run_id}


def _row_to_run(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "workflow_id": row.workflow_id,
        "status": row.status,
        "trigger_kind": row.trigger_kind,
        "trigger_payload": json.loads(row.trigger_payload or "{}"),
        "dry_run": bool(row.dry_run),
        "error": row.error,
        "cost_usd": row.cost_usd,
        "tokens_in": row.tokens_in,
        "tokens_out": row.tokens_out,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


_RUN_COLS = (
    "id, workflow_id, status, trigger_kind, trigger_payload, dry_run, error, "
    "cost_usd, tokens_in, tokens_out, created_at, started_at, finished_at"
)


@router.get("/runs")
async def list_runs(
    workflow_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": min(max(limit, 1), 200)}
    where: list[str] = []
    if workflow_id is not None:
        where.append("workflow_id = :wf")
        params["wf"] = workflow_id
    if status is not None:
        where.append("status = :status")
        params["status"] = status
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    async with get_session() as session:
        result = await session.execute(
            text(
                f"SELECT {_RUN_COLS} FROM runs {where_sql} "
                f"ORDER BY id DESC LIMIT :limit"
            ),
            params,
        )
        return [_row_to_run(row) for row in result.all()]


@router.get("/runs/{run_id}")
async def get_run(run_id: int) -> dict[str, Any]:
    async with get_session() as session:
        row = (
            await session.execute(
                text(f"SELECT {_RUN_COLS} FROM runs WHERE id=:id"), {"id": run_id}
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(404, detail="run not found")
        steps = (
            await session.execute(
                text(
                    "SELECT id, node_id, node_type, status, input, output, error, "
                    "cost_usd, started_at, finished_at FROM run_steps "
                    "WHERE run_id=:id ORDER BY id"
                ),
                {"id": run_id},
            )
        ).all()
    run = _row_to_run(row)
    run["steps"] = [
        {
            "id": s.id,
            "node_id": s.node_id,
            "node_type": s.node_type,
            "status": s.status,
            "input": json.loads(s.input or "{}"),
            "output": json.loads(s.output or "{}"),
            "error": s.error,
            "cost_usd": s.cost_usd,
            "started_at": s.started_at,
            "finished_at": s.finished_at,
        }
        for s in steps
    ]
    return run


@router.post("/runs/{run_id}/cancel", status_code=204)
async def cancel_run(run_id: int, request: Request) -> None:
    async with get_session() as session:
        row = (
            await session.execute(
                text("SELECT id, status FROM runs WHERE id=:id"), {"id": run_id}
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(404, detail="run not found")
    if row.status in ("succeeded", "failed", "cancelled", "budget_exceeded"):
        raise HTTPException(409, detail=f"run already {row.status}")
    await request.app.state.engine.cancel(run_id)
