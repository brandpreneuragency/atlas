"""Brain review queue routes (MASTER_PLAN §5, PHASE_7 Task 7.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import require_session
from app.files.safe_path import PathViolation
from app.review import service

router = APIRouter(prefix="/api", dependencies=[Depends(require_session)])


class DecideIn(BaseModel):
    decision: Literal["approved", "rejected"]


def _atlas_root(request: Request) -> Path:
    return Path(request.app.state.settings.atlas_root)


@router.get("/review")
async def list_review(request: Request) -> list[dict[str, Any]]:
    root = _atlas_root(request)
    return await anyio.to_thread.run_sync(service.list_pending, root)


@router.post("/review/{name}/decide")
async def decide_review(
    name: str, body: DecideIn, request: Request
) -> dict[str, str]:
    root = _atlas_root(request)
    try:
        path = service.note_path(root, name)
    except PathViolation as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(404, detail="review note not found")
    hermes = request.app.state.engine.hermes()
    run_id = await service.decide(name, body.decision, hermes)
    return {"run_id": run_id}
