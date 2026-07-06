"""Task 8.1 — backup status endpoint."""

from __future__ import annotations

import json


async def _login(client):
    response = await client.post("/api/auth/login", json={"password": "testpw"})
    assert response.status_code == 204


async def test_backup_status_no_backup_yet(app_client):
    await _login(app_client)
    response = await app_client.get("/api/settings/backup")
    assert response.status_code == 200
    assert response.json() == {"ok": False, "reason": "no backup yet"}


async def test_backup_status_returns_parsed_json(app_client, tmp_path):
    await _login(app_client)
    backups = tmp_path / "backups"
    backups.mkdir()
    status = {"ts": "2026-07-06T04:30:00+00:00", "ok": True, "size": 123456}
    (backups / "last-backup.json").write_text(json.dumps(status), encoding="utf-8")
    response = await app_client.get("/api/settings/backup")
    assert response.status_code == 200
    assert response.json() == status


async def test_backup_status_corrupt_file(app_client, tmp_path):
    await _login(app_client)
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "last-backup.json").write_text("{not json", encoding="utf-8")
    response = await app_client.get("/api/settings/backup")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "unreadable" in body["reason"]
