from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sse_starlette.sse import EventSourceResponse

from app.auth import require_session
from app.db import get_session
from app.events import broadcaster

router = APIRouter(prefix="/api")


async def _list_events(
    limit: int, before_id: int | None, kind: str | None
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    where: list[str] = []
    if before_id is not None:
        where.append("id < :before_id")
        params["before_id"] = before_id
    if kind is not None:
        where.append("kind = :kind")
        params["kind"] = kind
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    async with get_session() as session:
        result = await session.execute(
            text(
                f"SELECT id, ts, kind, source, agent_id, workflow_id, run_id, payload "
                f"FROM events {where_sql} "
                f"ORDER BY id DESC LIMIT :limit"
            ),
            params,
        )
        rows = result.all()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row.payload)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        out.append(
            {
                "id": row.id,
                "ts": row.ts,
                "kind": row.kind,
                "source": row.source,
                "agent_id": row.agent_id,
                "workflow_id": row.workflow_id,
                "run_id": row.run_id,
                "payload": payload,
            }
        )
    return out


@router.get("/events", dependencies=[Depends(require_session)])
async def list_events(
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None),
    kind: str | None = Query(None),
) -> list[dict[str, Any]]:
    return await _list_events(limit, before_id, kind)


async def _event_stream(queue: "asyncio.Queue[dict[str, Any]]") -> AsyncIterator[dict[str, Any]]:
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20.0)
            except asyncio.TimeoutError:
                # heartbeat comment keeps proxies from closing the idle stream
                yield {"comment": "ping"}
                continue
            yield {
                "event": "atlas",
                "data": json.dumps(event, separators=(",", ":"), default=str),
            }
    finally:
        broadcaster.unsubscribe(queue)


@router.get("/events/stream", dependencies=[Depends(require_session)])
async def events_stream() -> EventSourceResponse:
    # subscribe eagerly (before streaming starts) so events appended between the
    # response headers and the first client pull are not lost.
    queue = broadcaster.subscribe()
    return EventSourceResponse(_event_stream(queue), ping=20)