"""Email notification transport. Real send lands in Phase 7 — until then this
is a stub the workflow node calls (tests patch it)."""

from __future__ import annotations


async def send(subject: str, message: str) -> None:
    # Phase 7: read smtp_url/smtp_to from settings and send via SMTP.
    return None
