from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import get_session


class Broadcaster:
    """Fan-out queue manager for SSE subscribers.

    Slow consumers (queue full when ``put_nowait`` raises ``QueueFull``) are
    dropped immediately so a single stuck client can never stall the emitter.
    """

    def __init__(self, maxsize: int = 500) -> None:
        self._maxsize = maxsize
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # drop the slow consumer; it will reconnect via the SSE retry loop
                self._subscribers.discard(queue)

    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Module-level singleton: the SSE stream subscribes here, append_event publishes here.
broadcaster = Broadcaster()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def append_event(
    kind: str,
    source: str,
    summary: str,
    *,
    agent_id: int | None = None,
    workflow_id: int | None = None,
    run_id: int | None = None,
    **payload: Any,
) -> dict[str, Any]:
    """Persist an event row and broadcast it to live SSE subscribers.

    The ``summary`` is the human-readable feed line per MASTER_PLAN §8 and is
    embedded in ``payload`` (the events table records payload JSON only).
    """
    body: dict[str, Any] = {"summary": summary}
    body.update(payload)
    payload_json = json.dumps(body, separators=(",", ":"), default=str)

    async with get_session() as session:
        result = await session.execute(
            text(
                "INSERT INTO events(ts, kind, source, agent_id, workflow_id, run_id, payload) "
                "VALUES (:ts, :kind, :source, :agent_id, :workflow_id, :run_id, :payload) "
                "RETURNING id, ts"
            ),
            {
                "ts": _now_iso(),
                "kind": kind,
                "source": source,
                "agent_id": agent_id,
                "workflow_id": workflow_id,
                "run_id": run_id,
                "payload": payload_json,
            },
        )
        row = result.one()
        await session.commit()

    event: dict[str, Any] = {
        "id": row.id,
        "ts": row.ts,
        "kind": kind,
        "source": source,
        "agent_id": agent_id,
        "workflow_id": workflow_id,
        "run_id": run_id,
        "payload": body,
    }
    broadcaster.publish(event)
    return event