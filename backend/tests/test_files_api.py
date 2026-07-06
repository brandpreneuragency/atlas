import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

CSRF = {"X-Atlas-CSRF": "1"}


@pytest_asyncio.fixture
async def files_client(tmp_path):
    """Authenticated client with a small file tree jailed at atlas_root."""
    jail = tmp_path / "atlas"
    inbox = jail / "01_inbox"
    inbox.mkdir(parents=True)
    (inbox / "b.md").write_text("# note b\n", encoding="utf-8")
    (inbox / "a.md").write_text("# note a\n", encoding="utf-8")
    (jail / "02_processed").mkdir()
    (jail / "zz.txt").write_text("root file", encoding="utf-8")

    settings = Settings(
        data_dir=tmp_path,
        atlas_root=jail,
        password="testpw",
        secret_key="testsecret",
        mock_hermes=True,
        dev_mode=True,
        static_dir=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            login = await client.post("/api/auth/login", json={"password": "testpw"})
            assert login.status_code == 204
            client.jail = jail  # type: ignore[attr-defined]
            yield client


async def _events(client):
    response = await client.get("/api/events?limit=50")
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_tree_dirs_first_alphabetical(files_client):
    response = await files_client.get("/api/files/tree", params={"path": ""})
    assert response.status_code == 200
    entries = response.json()["entries"]
    names = [e["name"] for e in entries]
    assert names == ["01_inbox", "02_processed", "zz.txt"]
    assert entries[0]["is_dir"] is True
    assert entries[2]["is_dir"] is False
    assert entries[2]["size"] == len(b"root file")
    assert isinstance(entries[2]["mtime"], (int, float))


@pytest.mark.asyncio
async def test_tree_traversal_rejected(files_client):
    response = await files_client.get(
        "/api/files/tree", params={"path": "../../etc"}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_read_returns_content_and_mtime(files_client):
    response = await files_client.get(
        "/api/files/read", params={"path": "01_inbox/a.md"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "# note a\n"
    assert isinstance(body["mtime"], (int, float))
    assert body["truncated"] is False


@pytest.mark.asyncio
async def test_read_over_2mb_is_413(files_client):
    big = files_client.jail / "big.bin"
    big.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    response = await files_client.get("/api/files/read", params={"path": "big.bin"})
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_write_stale_mtime_conflicts_and_leaves_file(files_client):
    read = (
        await files_client.get("/api/files/read", params={"path": "01_inbox/a.md"})
    ).json()
    response = await files_client.put(
        "/api/files/write",
        json={
            "path": "01_inbox/a.md",
            "content": "LOST UPDATE",
            "expected_mtime": read["mtime"] - 100,
        },
        headers=CSRF,
    )
    assert response.status_code == 409
    assert (files_client.jail / "01_inbox" / "a.md").read_text() == "# note a\n"


@pytest.mark.asyncio
async def test_write_with_correct_mtime_saves_and_emits_event(files_client):
    read = (
        await files_client.get("/api/files/read", params={"path": "01_inbox/a.md"})
    ).json()
    response = await files_client.put(
        "/api/files/write",
        json={
            "path": "01_inbox/a.md",
            "content": "# updated\n",
            "expected_mtime": read["mtime"],
        },
        headers=CSRF,
    )
    assert response.status_code == 204
    assert (files_client.jail / "01_inbox" / "a.md").read_text() == "# updated\n"
    kinds = [e["kind"] for e in await _events(files_client)]
    assert "file.changed" in kinds


@pytest.mark.asyncio
async def test_write_null_mtime_creates_new_file(files_client):
    response = await files_client.put(
        "/api/files/write",
        json={"path": "01_inbox/new.md", "content": "new", "expected_mtime": None},
        headers=CSRF,
    )
    assert response.status_code == 204
    assert (files_client.jail / "01_inbox" / "new.md").read_text() == "new"


@pytest.mark.asyncio
async def test_mkdir_and_event(files_client):
    response = await files_client.post(
        "/api/files/mkdir", json={"path": "03_brain"}, headers=CSRF
    )
    assert response.status_code == 204
    assert (files_client.jail / "03_brain").is_dir()
    events = await _events(files_client)
    assert any(e["kind"] == "file.created" for e in events)


@pytest.mark.asyncio
async def test_move_refuses_overwrite_unless_flag(files_client):
    (files_client.jail / "02_processed" / "a.md").write_text("existing")
    body = {"paths": ["01_inbox/a.md"], "dest": "02_processed"}
    response = await files_client.post("/api/files/move", json=body, headers=CSRF)
    assert response.status_code == 409
    assert (files_client.jail / "01_inbox" / "a.md").exists()

    response = await files_client.post(
        "/api/files/move", json={**body, "overwrite": True}, headers=CSRF
    )
    assert response.status_code == 204
    assert not (files_client.jail / "01_inbox" / "a.md").exists()
    assert (files_client.jail / "02_processed" / "a.md").read_text() == "# note a\n"


@pytest.mark.asyncio
async def test_move_emits_summary_with_arrow(files_client):
    response = await files_client.post(
        "/api/files/move",
        json={"paths": ["01_inbox/a.md"], "dest": "02_processed"},
        headers=CSRF,
    )
    assert response.status_code == 204
    events = await _events(files_client)
    summaries = [e["payload"].get("summary", "") for e in events]
    assert any(
        s == "moved 01_inbox/a.md → 02_processed/a.md" for s in summaries
    )


@pytest.mark.asyncio
async def test_bulk_move_is_atomic_on_failure(files_client):
    # second path is invalid → NOTHING moves
    response = await files_client.post(
        "/api/files/move",
        json={"paths": ["01_inbox/a.md", "01_inbox/missing.md"], "dest": "02_processed"},
        headers=CSRF,
    )
    assert response.status_code == 400
    assert (files_client.jail / "01_inbox" / "a.md").exists()
    assert not (files_client.jail / "02_processed" / "a.md").exists()


@pytest.mark.asyncio
async def test_copy_keeps_source(files_client):
    response = await files_client.post(
        "/api/files/copy",
        json={"paths": ["01_inbox/a.md"], "dest": "02_processed"},
        headers=CSRF,
    )
    assert response.status_code == 204
    assert (files_client.jail / "01_inbox" / "a.md").exists()
    assert (files_client.jail / "02_processed" / "a.md").exists()


@pytest.mark.asyncio
async def test_delete_nonempty_dir_requires_recursive(files_client):
    response = await files_client.post(
        "/api/files/delete", json={"paths": ["01_inbox"]}, headers=CSRF
    )
    assert response.status_code == 400
    assert (files_client.jail / "01_inbox").is_dir()

    response = await files_client.post(
        "/api/files/delete",
        json={"paths": ["01_inbox"], "recursive": True},
        headers=CSRF,
    )
    assert response.status_code == 204
    assert not (files_client.jail / "01_inbox").exists()
    events = await _events(files_client)
    assert any(e["kind"] == "file.deleted" for e in events)


@pytest.mark.asyncio
async def test_upload_stores_file(files_client):
    response = await files_client.post(
        "/api/files/upload",
        data={"path": "01_inbox"},
        files={"file": ("up.txt", b"uploaded bytes", "text/plain")},
        headers=CSRF,
    )
    assert response.status_code == 201
    assert (files_client.jail / "01_inbox" / "up.txt").read_bytes() == b"uploaded bytes"
    events = await _events(files_client)
    assert any(e["kind"] == "file.created" for e in events)


@pytest.mark.asyncio
async def test_upload_rejects_jail_escape(files_client):
    response = await files_client.post(
        "/api/files/upload",
        data={"path": "../outside"},
        files={"file": ("up.txt", b"x", "text/plain")},
        headers=CSRF,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_bad_filename(files_client):
    response = await files_client.post(
        "/api/files/upload",
        data={"path": "01_inbox"},
        files={"file": ("../evil.txt", b"x", "text/plain")},
        headers=CSRF,
    )
    assert response.status_code == 400
