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
from app.hermes.admin import HermesAdmin
from app.hermes.factory import make_hermes_client
from app.hermes.schemas import HermesUnavailable
from app.routers.agents import _seed_default_agent

router = APIRouter()


def get_hermes_admin(request: Request) -> HermesAdmin:
    """Per-app HermesAdmin (token cache survives across requests)."""
    admin = getattr(request.app.state, "hermes_admin", None)
    if admin is None:
        admin = HermesAdmin(request.app.state.settings.hermes_admin_url)
        request.app.state.hermes_admin = admin
    return admin

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


# ---- Cron federation (proxied to HermesAdmin :9119) ----------------------


class CronSchedule(BaseModel):
    kind: str = "cron"
    expr: str


class CronCreateBody(BaseModel):
    name: str
    prompt: str
    schedule: CronSchedule
    skills: list[str] | None = None


def _validate_cron_expr(expr: str) -> None:
    from apscheduler.triggers.cron import (  # type: ignore[import-untyped]
        CronTrigger,
    )

    try:
        CronTrigger.from_crontab(expr)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid cron expression: {exc}"
        ) from exc


def _job_name(data: Any, fallback: str) -> str:
    if isinstance(data, dict) and isinstance(data.get("name"), str):
        return data["name"]
    return fallback


@router.get("/api/hermes/cron", dependencies=[Depends(require_session)])
async def cron_list(request: Request) -> list[dict[str, Any]]:
    try:
        return await get_hermes_admin(request).cron_jobs()
    except HermesUnavailable as exc:
        await append_event("hermes.error", "cron", f"cron list failed: {exc}")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/hermes/cron", dependencies=[Depends(require_session)])
async def cron_create(request: Request, body: CronCreateBody) -> dict[str, Any]:
    _validate_cron_expr(body.schedule.expr)
    try:
        job = await get_hermes_admin(request).cron_create(
            body.model_dump(exclude_none=True)
        )
    except HermesUnavailable as exc:
        await append_event("hermes.error", "cron", f"cron create failed: {exc}")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await append_event(
        "hermes.cron_changed", "cron", f"created cron job '{body.name}'"
    )
    return job


@router.put("/api/hermes/cron/{job_id}", dependencies=[Depends(require_session)])
async def cron_update(
    request: Request, job_id: str, patch: dict[str, Any]
) -> dict[str, Any]:
    schedule = patch.get("schedule")
    if isinstance(schedule, dict) and isinstance(schedule.get("expr"), str):
        _validate_cron_expr(schedule["expr"])
    try:
        job = await get_hermes_admin(request).cron_update(job_id, patch)
    except HermesUnavailable as exc:
        await append_event("hermes.error", "cron", f"cron update failed: {exc}")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await append_event(
        "hermes.cron_changed",
        "cron",
        f"updated cron job '{_job_name(job, job_id)}'",
    )
    return job


@router.post(
    "/api/hermes/cron/{job_id}/{action}",
    dependencies=[Depends(require_session)],
)
async def cron_action(request: Request, job_id: str, action: str) -> dict[str, Any]:
    admin = get_hermes_admin(request)
    actions = {
        "pause": (admin.cron_pause, "paused"),
        "resume": (admin.cron_resume, "resumed"),
        "trigger": (admin.cron_trigger, "triggered"),
    }
    if action not in actions:
        raise HTTPException(status_code=404, detail="unknown cron action")
    call, verb = actions[action]
    try:
        job = await call(job_id)
    except HermesUnavailable as exc:
        await append_event("hermes.error", "cron", f"cron {action} failed: {exc}")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await append_event(
        "hermes.cron_changed", "cron", f"{verb} '{_job_name(job, job_id)}'"
    )
    return job


@router.delete(
    "/api/hermes/cron/{job_id}",
    status_code=204,
    dependencies=[Depends(require_session)],
)
async def cron_delete(request: Request, job_id: str) -> None:
    admin = get_hermes_admin(request)
    name = job_id
    try:
        jobs = await admin.cron_jobs()
        name = next(
            (j["name"] for j in jobs if j.get("id") == job_id and "name" in j),
            job_id,
        )
        await admin.cron_delete(job_id)
    except HermesUnavailable as exc:
        await append_event("hermes.error", "cron", f"cron delete failed: {exc}")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await append_event(
        "hermes.cron_changed", "cron", f"deleted cron job '{name}'"
    )


# ---- Models / env / analytics / logs (proxied to HermesAdmin) ------------


class ModelSetBody(BaseModel):
    model: str
    provider: str


class EnvPutBody(BaseModel):
    key: str
    value: str


def _admin_502(exc: HermesUnavailable) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/api/hermes/model", dependencies=[Depends(require_session)])
async def model_get(request: Request) -> dict[str, Any]:
    admin = get_hermes_admin(request)
    try:
        info = await admin.model_info()
        options = await admin.model_options()
    except HermesUnavailable as exc:
        await append_event("hermes.error", "model", f"model fetch failed: {exc}")
        raise _admin_502(exc) from exc
    return {"current": info, "options": options}


@router.post("/api/hermes/model", dependencies=[Depends(require_session)])
async def model_set(request: Request, body: ModelSetBody) -> dict[str, Any]:
    try:
        result = await get_hermes_admin(request).model_set(body.model, body.provider)
    except HermesUnavailable as exc:
        await append_event("hermes.error", "model", f"model set failed: {exc}")
        raise _admin_502(exc) from exc
    await append_event(
        "hermes.cron_changed",
        "model",
        f"switched model to {body.model} ({body.provider})",
    )
    return result


@router.get("/api/hermes/env", dependencies=[Depends(require_session)])
async def env_list(request: Request) -> dict[str, Any]:
    try:
        # values arrive pre-masked from Hermes; we never unmask (no reveal route)
        return await get_hermes_admin(request).env_list()
    except HermesUnavailable as exc:
        raise _admin_502(exc) from exc


@router.put("/api/hermes/env", dependencies=[Depends(require_session)])
async def env_put(request: Request, body: EnvPutBody) -> dict[str, Any]:
    try:
        result = await get_hermes_admin(request).env_put(body.key, body.value)
    except HermesUnavailable as exc:
        raise _admin_502(exc) from exc
    await append_event("hermes.cron_changed", "env", f"set provider key {body.key}")
    return result


@router.delete("/api/hermes/env/{key}", dependencies=[Depends(require_session)])
async def env_delete(request: Request, key: str) -> dict[str, Any]:
    try:
        result = await get_hermes_admin(request).env_delete(key)
    except HermesUnavailable as exc:
        raise _admin_502(exc) from exc
    await append_event("hermes.cron_changed", "env", f"deleted provider key {key}")
    return result


@router.get(
    "/api/hermes/analytics/usage", dependencies=[Depends(require_session)]
)
async def analytics_usage(request: Request) -> dict[str, Any]:
    try:
        return await get_hermes_admin(request).analytics_usage()
    except HermesUnavailable as exc:
        raise _admin_502(exc) from exc


@router.get(
    "/api/hermes/analytics/models", dependencies=[Depends(require_session)]
)
async def analytics_models(request: Request) -> dict[str, Any]:
    try:
        return await get_hermes_admin(request).analytics_models()
    except HermesUnavailable as exc:
        raise _admin_502(exc) from exc


@router.get("/api/hermes/logs", dependencies=[Depends(require_session)])
async def hermes_logs(request: Request, tail: int = 200) -> Response:
    try:
        text_body = await get_hermes_admin(request).logs(tail=tail)
    except HermesUnavailable as exc:
        raise _admin_502(exc) from exc
    return Response(content=text_body, media_type="text/plain")


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