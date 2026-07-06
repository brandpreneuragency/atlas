from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _migration_dir() -> Path:
    return Path(__file__).parent / "migrations"


async def init_db(path: str | Path) -> AsyncEngine:
    global _engine, _sessionmaker

    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        )
        applied = set(
            (
                await conn.execute(text("SELECT version FROM schema_migrations"))
            ).scalars().all()
        )
        for migration in sorted(_migration_dir().glob("*.sql")):
            version = int(migration.name.split("_", 1)[0])
            if version in applied:
                continue
            for statement in migration.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    await conn.exec_driver_sql(statement)
            await conn.execute(
                text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                {"version": version},
            )

    _engine = engine
    _sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return engine


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Database has not been initialized")
    async with _sessionmaker() as session:
        yield session
