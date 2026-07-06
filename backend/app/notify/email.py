"""Email notification transport (PHASE_7 Task 7.1).

Reads ``smtp_url`` (``smtp://user:pass@host:port``) and ``smtp_to`` from the
settings table and sends via aiosmtplib. Missing config returns ``False``.
"""

from __future__ import annotations

from email.message import EmailMessage
from urllib.parse import unquote, urlparse

import aiosmtplib
from sqlalchemy import text as sql

from app.db import get_session
from app.events import append_event


async def _setting(key: str) -> str | None:
    async with get_session() as session:
        return (
            await session.execute(
                sql("SELECT value FROM settings WHERE key = :k"), {"k": key}
            )
        ).scalar_one_or_none()


async def send(subject: str, message: str) -> bool:
    smtp_url = await _setting("smtp_url")
    smtp_to = await _setting("smtp_to")
    if not smtp_url or not smtp_to:
        return False

    parsed = urlparse(smtp_url)
    username = unquote(parsed.username) if parsed.username else None
    sender = username if username and "@" in username else f"atlas@{parsed.hostname}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = smtp_to
    msg.set_content(message)

    try:
        await aiosmtplib.send(
            msg,
            hostname=parsed.hostname,
            port=parsed.port or 587,
            username=username,
            password=unquote(parsed.password) if parsed.password else None,
            use_tls=parsed.scheme == "smtps",
            start_tls=None if parsed.scheme == "smtps" else True,
        )
    except Exception as exc:  # aiosmtplib raises a family of SMTP errors
        await append_event("system.error", "notify", f"email send failed: {exc}")
        return False
    return True
