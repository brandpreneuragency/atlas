import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sse_starlette.sse import EventSourceResponse

from app.auth import require_session
from app.db import get_session
from app.events import append_event
from app.hermes.factory import make_hermes_client
from app.hermes.schemas import HermesUnavailable
from app.routers.agents import _seed_default_agent

router = APIRouter()

_HOP_BY_HOP_HEADERS = {
    "host",
    "content-length",
    "connection",
    "transfer-encoding",
}


@router.api_route(
    "/hermes/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def hermes_proxy(
    path: str,
    request: Request,
    _session: Annotated[dict[str, str], Depends(require_session)],
) -> Response:
    if request.headers.get("upgrade", "").lower() == "websocket":
        raise HTTPException(
            status_code=501,
            detail="hermes websockets not proxied; native views coming in Phase 2",
        )

    settings = request.app.state.settings
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }
    url = httpx.URL(f"{settings.hermes_admin_url.rstrip('/')}/{path}").copy_with(
        query=request.url.query.encode("utf-8")
    )
    async with httpx.AsyncClient(timeout=None) as client:
        upstream = await client.request(
            request.method,
            url,
            content=await request.body(),
            headers=headers,
        )
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


# ---- Native Hermes surface (sessions, chat) ------------------------------


class ChatRequest(BaseModel):
    thread_id: int | None = None
    message: str


def _client(settings: Any):
    return make_hermes_client(settings, timeout_s=10.0)


@router.get(
    "/api/hermes/sessions",
    dependencies=[Depends(require_session)],
)
async def hermes_sessions(
    request: Request,
    q: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    settings = request.app.state.settings
    try:
        sessions = await _client(settings).sessions(q=q, limit=limit)
    except HermesUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return sessions


@router.get(
    "/api/hermes/sessions/{sid}/messages",
    dependencies=[Depends(require_session)],
)
async def hermes_session_messages(
    sid: str, request: Request
) -> list[dict[str, Any]]:
    settings = request.app.state.settings
    try:
        return await _client(settings).session_messages(sid)
    except HermesUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _get_default_agent_id(request: Request) -> int:
    await _seed_default_agent(request)
    async with get_session() as session:
        row = (
            await session.execute(
                text("SELECT id FROM agents WHERE name = 'Hermes' LIMIT 1")
            )
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=500, detail="no default agent seeded")
    return int(row)


async def _resolve_or_create_thread(
    request: Request, thread_id: int | None
) -> tuple[int, str]:
    """Resolve a chat thread → (thread_id, hermes_session_id).

    On first message (``thread_id is None``) a Hermes session is created and a
    ``chat_threads`` row is inserted.
    """
    settings = request.app.state.settings
    agent_id = await _get_default_agent_id(request)

    if thread_id is not None:
        async with get_session() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT id, hermes_session_id FROM chat_threads "
                        "WHERE id = :tid AND agent_id = :aid"
                    ),
                    {"tid": thread_id, "aid": agent_id},
                )
            ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="thread not found")
        return int(row.id), row.hermes_session_id

    # first message → create Hermes session + thread row
    try:
        sid = await _client(settings).create_session()
    except HermesUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    async with get_session() as session:
        result = await session.execute(
            text(
                "INSERT INTO chat_threads(hermes_session_id, agent_id, title, created_at) "
                "VALUES (:sid, :aid, :title, :ts) RETURNING id"
            ),
            {
                "sid": sid,
                "aid": agent_id,
                "title": "New chat",
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        new_id = int(result.scalar_one())
        await session.commit()
    return new_id, sid


@router.get(
    "/api/hermes/threads",
    dependencies=[Depends(require_session)],
)
async def hermes_threads(request: Request) -> list[dict[str, Any]]:
    agent_id = await _get_default_agent_id(request)
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, hermes_session_id, agent_id, title, created_at "
                    "FROM chat_threads WHERE agent_id = :aid ORDER BY id DESC"
                ),
                {"aid": agent_id},
            )
        ).all()
    return [
        {
            "id": r.id,
            "hermes_session_id": r.hermes_session_id,
            "agent_id": r.agent_id,
            "title": r.title,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post(
    "/api/hermes/chat",
    dependencies=[Depends(require_session)],
)
async def hermes_chat(
    payload: ChatRequest, request: Request
) -> EventSourceResponse:
    settings = request.app.state.settings
    thread_id, sid = await _resolve_or_create_thread(request, payload.thread_id)

    async def stream() -> AsyncIterator[dict[str, Any]]:
        full_text: list[str] = []
        try:
            async for chunk in _client(settings).chat_stream(sid, payload.message):
                full_text.append(chunk)
                yield {"event": "token", "data": chunk}
        except HermesUnavailable as exc:
            yield {"event": "error", "data": str(exc)}
        # feed visibility for the run/chat lifecycle
        await append_event(
            "hermes.run_event",
            "chat",
            f"chat reply ({len(''.join(full_text))} chars)",
            agent_id=await _get_default_agent_id(request),
            run_id=None,
            thread_id=thread_id,
            session_id=sid,
        )
        yield {"event": "done", "data": json.dumps({"thread_id": thread_id})}

    # EventSourceResponse subscribes the generator eagerly if we hand it a
    # coroutine-free async generator; we keep it simple — the chat stream is
    # finite (ends on `done`) so ESITransport-free tests use stream_client.
    return EventSourceResponse(stream(), ping=20)