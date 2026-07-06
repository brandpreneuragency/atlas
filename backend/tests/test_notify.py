"""Task 7.1 — notification transports + settings wiring (PHASE_7)."""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy import text

from app.db import get_session
from app.notify import email as email_notify
from app.notify import telegram as telegram_notify

CSRF = {"X-Atlas-CSRF": "1"}


async def _login(client):
    response = await client.post("/api/auth/login", json={"password": "testpw"})
    assert response.status_code == 204


async def _set_setting(key: str, value: str) -> None:
    async with get_session() as session:
        await session.execute(
            text(
                "INSERT INTO settings(key, value) VALUES (:k, :v) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            ),
            {"k": key, "v": value},
        )
        await session.commit()


async def _event_count(kind: str) -> int:
    async with get_session() as session:
        return (
            await session.execute(
                text("SELECT COUNT(*) FROM events WHERE kind = :k"), {"k": kind}
            )
        ).scalar_one()


@pytest.fixture(autouse=True)
def _reset_notify_state():
    telegram_notify.reset_warning()
    yield
    telegram_notify.reset_warning()


@respx.mock
async def test_telegram_send_posts_plain_text(app_client):
    await _set_setting("telegram_bot_token", "TOK123")
    await _set_setting("telegram_chat_id", "42")
    route = respx.post("https://api.telegram.org/botTOK123/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    assert await telegram_notify.send("hello *world*") is True
    assert route.called
    body = route.calls.last.request.read()
    import json

    payload = json.loads(body)
    assert payload["chat_id"] == "42"
    assert payload["text"] == "hello *world*"
    # plain text: Markdown must be disabled (no parse_mode sent)
    assert "parse_mode" not in payload


async def test_telegram_missing_token_returns_false_single_error_event(app_client):
    before = await _event_count("system.error")
    assert await telegram_notify.send("one") is False
    assert await telegram_notify.send("two") is False
    after = await _event_count("system.error")
    assert after == before + 1  # warned once, not spammed


@respx.mock
async def test_telegram_api_failure_returns_false(app_client):
    await _set_setting("telegram_bot_token", "TOK123")
    await _set_setting("telegram_chat_id", "42")
    respx.post("https://api.telegram.org/botTOK123/sendMessage").mock(
        return_value=httpx.Response(500, json={"ok": False})
    )
    assert await telegram_notify.send("hello") is False


async def test_email_send_uses_smtp_url(app_client, monkeypatch):
    await _set_setting("smtp_url", "smtp://user:pw@mail.example.com:2525")
    await _set_setting("smtp_to", "dest@example.com")
    calls: list[dict] = []

    async def fake_send(message, **kwargs):
        calls.append({"message": message, **kwargs})

    monkeypatch.setattr(email_notify.aiosmtplib, "send", fake_send)
    assert await email_notify.send("Subject line", "Body text") is True
    assert len(calls) == 1
    call = calls[0]
    assert call["hostname"] == "mail.example.com"
    assert call["port"] == 2525
    assert call["username"] == "user"
    assert call["password"] == "pw"
    msg = call["message"]
    assert msg["Subject"] == "Subject line"
    assert msg["To"] == "dest@example.com"
    assert "Body text" in msg.get_content()


async def test_email_missing_config_returns_false(app_client):
    assert await email_notify.send("s", "b") is False


async def test_settings_notifications_roundtrip(app_client):
    await _login(app_client)
    put = await app_client.put(
        "/api/settings/notifications",
        json={
            "telegram_bot_token": "TOK",
            "telegram_chat_id": "42",
            "smtp_url": "smtp://u:p@h:25",
            "smtp_to": "a@b.c",
        },
        headers=CSRF,
    )
    assert put.status_code == 200
    got = await app_client.get("/api/settings/notifications")
    assert got.status_code == 200
    data = got.json()
    # secrets never echoed back — only set/not-set
    assert data["telegram_bot_token_set"] is True
    assert data["smtp_url_set"] is True
    assert data["telegram_chat_id"] == "42"
    assert data["smtp_to"] == "a@b.c"
    assert "telegram_bot_token" not in data
    assert "smtp_url" not in data


async def test_settings_notifications_partial_update_keeps_token(app_client):
    await _login(app_client)
    await app_client.put(
        "/api/settings/notifications",
        json={"telegram_bot_token": "TOK", "telegram_chat_id": "42"},
        headers=CSRF,
    )
    # update chat id only; omitted token must survive
    await app_client.put(
        "/api/settings/notifications",
        json={"telegram_chat_id": "43"},
        headers=CSRF,
    )
    got = (await app_client.get("/api/settings/notifications")).json()
    assert got["telegram_bot_token_set"] is True
    assert got["telegram_chat_id"] == "43"


@respx.mock
async def test_settings_notifications_test_endpoint(app_client):
    await _login(app_client)
    await _set_setting("telegram_bot_token", "TOK")
    await _set_setting("telegram_chat_id", "42")
    route = respx.post("https://api.telegram.org/botTOK/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    response = await app_client.post(
        "/api/settings/notifications/test", headers=CSRF
    )
    assert response.status_code == 200
    result = response.json()
    assert result["telegram"] is True
    assert result["email"] is False  # not configured
    assert route.called
    import json

    payload = json.loads(route.calls.last.request.read())
    assert payload["text"] == "ATLAS Control test message"
