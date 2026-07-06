import pytest
from sqlalchemy import text

from app.db import get_session, init_db


@pytest.mark.asyncio
async def test_migrations_apply_and_wal(tmp_path):
    engine = await init_db(tmp_path / "test.db")
    async with get_session() as s:
        tables = (
            await s.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            )
        ).scalars().all()
        assert {"settings", "agents", "events", "schema_migrations"} <= set(tables)
        mode = (await s.execute(text("PRAGMA journal_mode"))).scalar()
        assert mode == "wal"
    await engine.dispose()
