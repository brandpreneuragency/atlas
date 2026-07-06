from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from app.auth import require_session
from app.db import get_session
from app.hermes.factory import make_hermes_client
from app.hermes.schemas import HermesUnavailable

router = APIRouter(prefix="/api")


async def _seed_default_agent(request: Request) -> None:
    """First-boot seed: if the agents table is empty, insert the default
    Hermes agent whose URLs come from settings (MASTER_PLAN §5)."""
    settings = request.app.state.settings
    async with get_session() as session:
        count = (
            await session.execute(text("SELECT COUNT(*) FROM agents"))
        ).scalar_one()
        if count:
            return
        await session.execute(
            text(
                "INSERT INTO agents(name, kind, runs_url, admin_url, api_key_env, enabled, created_at) "
                "VALUES (:name, 'hermes', :runs_url, :admin_url, 'ATLAS_HERMES_API_KEY', 1, datetime('now'))"
            ),
            {
                "name": "Hermes",
                "runs_url": settings.hermes_runs_url,
                "admin_url": settings.hermes_admin_url,
            },
        )
        await session.commit()


async def _agent_card(
    request: Request, row: Any, settings: Any
) -> dict[str, Any]:
    card: dict[str, Any] = {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "runs_url": row.runs_url,
        "admin_url": row.admin_url,
        "api_key_env": row.api_key_env,
        "enabled": bool(row.enabled),
        "created_at": row.created_at,
        "status": "ok",
        "model": None,
        "active_runs": 0,
        "health": None,
    }
    # Override the client base URL with the per-agent runs_url so the table
    # remains the source of truth (settings only seeds the default).
    client = make_hermes_client(settings, timeout_s=3.0)
    if not settings.mock_hermes:
        # point real client at the agent's own runs URL
        client.base_url = row.runs_url  # type: ignore[attr-defined]
    try:
        health = await client.health()
        card["health"] = health
        card["active_runs"] = int(health.get("active_agents", 0) or 0)
        if settings.mock_hermes:
            card["model"] = "mock-model"
        else:  # pragma: no cover - exercised live in Phase 2.6
            from app.hermes.admin import HermesAdmin

            try:
                info = await HermesAdmin(row.admin_url).model_info()
                card["model"] = info.get("model")
            except HermesUnavailable:
                card["model"] = None
    except HermesUnavailable:
        card["status"] = "unreachable"
        card["active_runs"] = 0
        card["health"] = None
    return card


@router.get("/agents", dependencies=[Depends(require_session)])
async def list_agents(request: Request) -> list[dict[str, Any]]:
    await _seed_default_agent(request)
    settings = request.app.state.settings
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, name, kind, runs_url, admin_url, api_key_env, "
                    "enabled, created_at FROM agents ORDER BY id"
                )
            )
        ).all()
    return [await _agent_card(request, row, settings) for row in rows]