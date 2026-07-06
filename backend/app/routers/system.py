import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import require_session
from app.db import get_session
from app.hermes.client import HermesClient
from app.hermes.schemas import HermesUnavailable

router = APIRouter(prefix="/api")


class KillSwitchRequest(BaseModel):
    paused: bool


class ModelPrefs(BaseModel):
    favorites: list[str]
    hidden: list[str]


async def _setting(key: str) -> str | None:
    async with get_session() as session:
        return (
            await session.execute(
                text("SELECT value FROM settings WHERE key = :key"), {"key": key}
            )
        ).scalar_one_or_none()


async def _set_setting(key: str, value: str) -> None:
    async with get_session() as session:
        await session.execute(
            text(
                "INSERT INTO settings(key, value) VALUES (:key, :value) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            ),
            {"key": key, "value": value},
        )
        await session.commit()


@router.get("/settings/model-prefs", dependencies=[Depends(require_session)])
async def get_model_prefs() -> ModelPrefs:
    raw = await _setting("model_prefs")
    if raw is None:
        return ModelPrefs(favorites=[], hidden=[])
    return ModelPrefs.model_validate_json(raw)


@router.put("/settings/model-prefs", dependencies=[Depends(require_session)])
async def put_model_prefs(prefs: ModelPrefs) -> ModelPrefs:
    await _set_setting("model_prefs", json.dumps(prefs.model_dump()))
    return prefs


async def _paused() -> bool:
    async with get_session() as session:
        value = (
            await session.execute(
                text("SELECT value FROM settings WHERE key = 'global_pause'")
            )
        ).scalar_one_or_none()
    return value == "1"


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    if settings.mock_hermes:
        hermes = {"runs_api": "mock"}
    else:
        try:
            await HermesClient(
                settings.hermes_runs_url, settings.hermes_api_key, timeout_s=3.0
            ).health()
            hermes = {"runs_api": "ok"}
        except HermesUnavailable as exc:
            hermes = {"runs_api": f"unreachable: {exc}"}
    return {"status": "ok", "db": "ok", "hermes": hermes, "version": "0.1.0"}


@router.get("/me", dependencies=[Depends(require_session)])
async def me() -> dict[str, bool]:
    return {"authenticated": True}


@router.get("/killswitch", dependencies=[Depends(require_session)])
async def get_killswitch() -> dict[str, bool]:
    return {"paused": await _paused()}


@router.post("/killswitch", dependencies=[Depends(require_session)])
async def set_killswitch(
    payload: KillSwitchRequest, request: Request
) -> dict[str, bool]:
    from app.events import append_event
    from app.routers.hermes import get_hermes_admin

    already = await _paused()
    if payload.paused == already:
        # idempotent: engaging twice / releasing twice does nothing extra
        return {"paused": payload.paused}

    admin = get_hermes_admin(request)

    if payload.paused:
        paused_ids: list[str] = []
        try:
            jobs = await admin.cron_jobs()
        except HermesUnavailable as exc:
            await append_event(
                "hermes.error", "killswitch", f"cron list failed: {exc}"
            )
            jobs = []
        for job in jobs:
            if job.get("enabled") and isinstance(job.get("id"), str):
                try:
                    await admin.cron_pause(job["id"])
                    paused_ids.append(job["id"])
                except HermesUnavailable as exc:
                    await append_event(
                        "hermes.error",
                        "killswitch",
                        f"pause {job['id']} failed: {exc}",
                    )
        await _set_setting("killswitch_paused_jobs", json.dumps(paused_ids))
        await _set_setting("global_pause", "1")
        await append_event(
            "system.killswitch",
            "system",
            f"kill switch ENGAGED ({len(paused_ids)} Hermes job(s) paused)",
        )
    else:
        raw = await _setting("killswitch_paused_jobs")
        paused_ids = json.loads(raw) if raw else []
        resumed = 0
        for job_id in paused_ids:
            try:
                await admin.cron_resume(job_id)
                resumed += 1
            except HermesUnavailable as exc:
                await append_event(
                    "hermes.error",
                    "killswitch",
                    f"resume {job_id} failed: {exc}",
                )
        await _set_setting("killswitch_paused_jobs", "[]")
        await _set_setting("global_pause", "0")
        await append_event(
            "system.killswitch",
            "system",
            f"kill switch released ({resumed} Hermes job(s) resumed)",
        )
    return {"paused": payload.paused}
