"""Telegram notification transport. Real send lands in Phase 7 — until then
this is a stub the workflow node calls (tests patch it)."""

from __future__ import annotations


async def send(message: str) -> None:
    # Phase 7: read telegram_bot_token/telegram_chat_id from settings and POST
    # to the Bot API. Stub is a deliberate no-op until then.
    return None
