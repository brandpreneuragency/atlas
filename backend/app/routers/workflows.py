"""Workflow CRUD + versioning routes (MASTER_PLAN §5, PHASE_5 Task 5.1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from app.auth import require_session
from app.db import get_session
from app.engine.schemas import Graph, validate_graph

router = APIRouter(prefix="/api", dependencies=[Depends(require_session)])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    graph: dict[str, Any]
    max_runs_per_hour: int = 6
    budget_usd_per_run: float | None = None


class EnableIn(BaseModel):
    enabled: bool


class RollbackIn(BaseModel):
    version: int


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


@router.get("/workflows")
async def list_workflows() -> list[dict[str, Any]]:
    async with get_session() as session:
        result = await session.execute(
            text(f"SELECT {_WF_COLS} FROM workflows ORDER BY id")
        )
        return [_row_to_workflow(row) for row in result.all()]


@router.post("/workflows", status_code=201)
async def create_workflow(body: WorkflowIn) -> dict[str, Any]:
    _parse_and_validate(body.graph)
    graph_json = json.dumps(body.graph, separators=(",", ":"))
    now = _now_iso()
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
                "mrph": body.max_runs_per_hour,
                "budget": body.budget_usd_per_run,
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
async def update_workflow(workflow_id: int, body: WorkflowIn) -> dict[str, Any]:
    _parse_and_validate(body.graph)
    graph_json = json.dumps(body.graph, separators=(",", ":"))
    async with get_session() as session:
        row = await _fetch_workflow(session, workflow_id)
        new_version = row.version + 1
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
                "mrph": body.max_runs_per_hour,
                "budget": body.budget_usd_per_run,
                "now": _now_iso(),
                "id": workflow_id,
            },
        )
        await _snapshot_version(session, workflow_id, new_version, graph_json)
        await session.commit()
        return _row_to_workflow(await _fetch_workflow(session, workflow_id))


@router.delete("/workflows/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: int) -> None:
    async with get_session() as session:
        await _fetch_workflow(session, workflow_id)
        await session.execute(
            text("DELETE FROM workflows WHERE id=:id"), {"id": workflow_id}
        )
        await session.commit()


@router.post("/workflows/{workflow_id}/enable")
async def enable_workflow(workflow_id: int, body: EnableIn) -> dict[str, Any]:
    async with get_session() as session:
        await _fetch_workflow(session, workflow_id)
        await session.execute(
            text("UPDATE workflows SET enabled=:e, updated_at=:now WHERE id=:id"),
            {"e": int(body.enabled), "now": _now_iso(), "id": workflow_id},
        )
        await session.commit()
        return _row_to_workflow(await _fetch_workflow(session, workflow_id))


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
async def rollback_workflow(workflow_id: int, body: RollbackIn) -> dict[str, Any]:
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
        return _row_to_workflow(await _fetch_workflow(session, workflow_id))
