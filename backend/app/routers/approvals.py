"""Approvals routes (MASTER_PLAN §5) — resolving a gate resumes its run."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import require_session
from app.db import get_session

router = APIRouter(prefix="/api", dependencies=[Depends(require_session)])

_COLS = (
    "id, run_id, step_id, kind, external_ref, message, status, "
    "requested_at, resolved_at, resolved_via"
)


class ResolveIn(BaseModel):
    decision: Literal["approved", "rejected"]


def _row(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "step_id": row.step_id,
        "kind": row.kind,
        "external_ref": row.external_ref,
        "message": row.message,
        "status": row.status,
        "requested_at": row.requested_at,
        "resolved_at": row.resolved_at,
        "resolved_via": row.resolved_via,
    }


@router.get("/approvals")
async def list_approvals(status: str | None = None) -> list[dict[str, Any]]:
    where = "WHERE status = :status" if status else ""
    params = {"status": status} if status else {}
    async with get_session() as session:
        result = await session.execute(
            text(f"SELECT {_COLS} FROM approvals {where} ORDER BY id DESC"), params
        )
        return [_row(r) for r in result.all()]


@router.post("/approvals/{approval_id}/resolve")
async def resolve_approval(
    approval_id: int, body: ResolveIn, request: Request
) -> dict[str, Any]:
    async with get_session() as session:
        row = (
            await session.execute(
                text(f"SELECT {_COLS} FROM approvals WHERE id=:id"), {"id": approval_id}
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(404, detail="approval not found")
    if row.status != "pending":
        raise HTTPException(409, detail=f"approval already {row.status}")

    # engine.resume resolves the approval row and continues the run
    await request.app.state.engine.resume(row.run_id, body.decision)
    async with get_session() as session:
        updated = (
            await session.execute(
                text(f"SELECT {_COLS} FROM approvals WHERE id=:id"), {"id": approval_id}
            )
        ).one()
    return _row(updated)
