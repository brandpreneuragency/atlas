"""Telegram notification transport (PHASE_7 Task 7.1).

Reads ``telegram_bot_token`` / ``telegram_chat_id`` from the settings table and
POSTs plain text to the Bot API (Markdown deliberately disabled — no
``parse_mode`` — to avoid escaping bugs). Missing config returns ``False`` and
appends a single ``system.error`` event (not one per call).
"""

from __future__ import annotations

import httpx
from sqlalchemy import text as sql

from app.db import get_session
from app.events import append_event

_warned_missing = False


def reset_warning() -> None:
    """Re-arm the missing-config warning (used by tests and settings updates)."""
    global _warned_missing
    _warned_missing = False


async def _setting(key: str) -> str | None:
    async with get_session() as session:
        return (
            await session.execute(
                sql("SELECT value FROM settings WHERE key = :k"), {"k": key}
            )
        ).scalar_one_or_none()


async def send(message: str) -> bool:
    global _warned_missing
    token = await _setting("telegram_bot_token")
    chat_id = await _setting("telegram_chat_id")
    if not token or not chat_id:
        if not _warned_missing:
            _warned_missing = True
            await append_event(
                "system.error",
                "notify",
                "telegram notification skipped: bot token / chat id not configured",
            )
        return False
    _warned_missing = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
            )
    except httpx.HTTPError as exc:
        await append_event(
            "system.error", "notify", f"telegram send failed: {exc}"
        )
        return False
    if response.status_code != 200:
        await append_event(
            "system.error",
            "notify",
            f"telegram send failed: HTTP {response.status_code}",
        )
        return False
    return True
