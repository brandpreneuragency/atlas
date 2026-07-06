"""Engine guards (PHASE_5 Task 5.4): provenance loop-guard, circuit breaker,
budget accounting."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from app.db import get_session


class Provenance:
    """Paths recently written by the engine never re-trigger file-drop
    workflows (loop guard). Entries expire after ``ttl_s`` (default 60s)."""

    def __init__(self, ttl_s: float = 60.0) -> None:
        self._ttl_s = ttl_s
        self._paths: dict[str, float] = {}

    def _normalize(self, path: str) -> str:
        return path.replace("\\", "/").rstrip("/")

    def mark(self, path: str) -> None:
        self._paths[self._normalize(path)] = time.monotonic() + self._ttl_s

    def check(self, path: str) -> bool:
        """True if ``path`` was marked within the TTL."""
        now = time.monotonic()
        # prune expired entries so the dict cannot grow unbounded
        for key in [k for k, expiry in self._paths.items() if expiry <= now]:
            del self._paths[key]
        return self._normalize(path) in self._paths


class CircuitBreaker:
    """Refuses runs once a workflow exceeds its runs-per-hour cap."""

    async def check(self, workflow_id: int) -> bool:
        """True if another run is allowed right now."""
        async with get_session() as session:
            row = (
                await session.execute(
                    text("SELECT max_runs_per_hour FROM workflows WHERE id=:id"),
                    {"id": workflow_id},
                )
            ).one()
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            count = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM runs "
                        "WHERE workflow_id=:wf AND created_at >= :cutoff"
                    ),
                    {"wf": workflow_id, "cutoff": cutoff},
                )
            ).scalar_one()
        return count < row.max_runs_per_hour


class Budget:
    """Per-run USD budget accounting (cost model lives in engine.py)."""

    async def check_and_add(
        self, run: Any, usage: dict[str, Any], cost_usd: float
    ) -> bool:
        """Add ``cost_usd`` to the run; True if still within budget."""
        async with get_session() as session:
            await session.execute(
                text(
                    "UPDATE runs SET cost_usd = cost_usd + :c, "
                    "tokens_in = tokens_in + :ti, tokens_out = tokens_out + :to_ "
                    "WHERE id=:id"
                ),
                {
                    "c": cost_usd,
                    "ti": int(usage.get("input_tokens", 0)),
                    "to_": int(usage.get("output_tokens", 0)),
                    "id": run.id,
                },
            )
            await session.commit()
            row = (
                await session.execute(
                    text(
                        "SELECT r.cost_usd, w.budget_usd_per_run FROM runs r "
                        "JOIN workflows w ON w.id = r.workflow_id WHERE r.id=:id"
                    ),
                    {"id": run.id},
                )
            ).one()
        if row.budget_usd_per_run is None:
            return True
        return bool(row.cost_usd <= row.budget_usd_per_run)
