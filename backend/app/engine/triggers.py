"""Trigger service (PHASE_5 Task 5.4): cron scheduling, file-drop watching,
webhook rate limiting. Manual + webhook HTTP routes live in routers/workflows.py.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from sqlalchemy import text

from app.config import Settings
from app.db import get_session
from app.engine.engine import EnginePaused
from app.engine.guards import Provenance

# Sync/temp artifacts that must never trigger a workflow.
IGNORE_PATTERNS = (".syncthing.*", "*.tmp", ".stfolder", ".trash*")

MISFIRE_GRACE_S = 300


class HookRateLimiter:
    """Per-workflow webhook rate limit: 10 requests per minute."""

    def __init__(self, limit: int = 10, window_s: float = 60.0) -> None:
        self._limit = limit
        self._window_s = window_s
        self._hits: dict[int, deque[float]] = {}

    def allow(self, workflow_id: int) -> bool:
        now = time.monotonic()
        hits = self._hits.setdefault(workflow_id, deque())
        while hits and hits[0] <= now - self._window_s:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True


class TriggerService:
    def __init__(self, engine: Any, settings: Settings) -> None:
        self._engine = engine
        self._settings = settings
        self.scheduler = AsyncIOScheduler(timezone=settings.tz)
        self.provenance = Provenance()
        self.hook_limiter = HookRateLimiter()
        # file-drop routing table, rebuilt by sync(): (wf_id, watch_path, glob, stability_s)
        self._file_watches: list[tuple[int, str, str, float]] = []
        self._debounce: dict[tuple[int, str], asyncio.TimerHandle] = {}
        self._watch_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ sync

    async def sync(self) -> None:
        """Reconcile scheduler jobs + file-drop routes with enabled workflows."""
        async with get_session() as session:
            rows = (
                await session.execute(
                    text("SELECT id, graph, enabled FROM workflows")
                )
            ).all()

        wanted_jobs: set[str] = set()
        file_watches: list[tuple[int, str, str, float]] = []
        for row in rows:
            if not row.enabled:
                continue
            try:
                graph = json.loads(row.graph)
            except json.JSONDecodeError:
                continue
            for node in graph.get("nodes", []):
                config = node.get("config", {})
                if node.get("type") == "trigger.cron":
                    job_id = f"wf-{row.id}"
                    wanted_jobs.add(job_id)
                    self.scheduler.add_job(
                        self.fire_cron,
                        CronTrigger.from_crontab(
                            str(config["expr"]), timezone=self._settings.tz
                        ),
                        args=[row.id],
                        id=job_id,
                        misfire_grace_time=MISFIRE_GRACE_S,
                        replace_existing=True,
                    )
                elif node.get("type") == "trigger.file_drop":
                    file_watches.append(
                        (
                            row.id,
                            str(config["watch_path"]).strip("/"),
                            str(config.get("glob", "*")),
                            float(config.get("stability_s", 5)),
                        )
                    )

        for job in self.scheduler.get_jobs():
            if job.id.startswith("wf-") and job.id not in wanted_jobs:
                self.scheduler.remove_job(job.id)
        self._file_watches = file_watches

    # ------------------------------------------------------------------ cron

    async def fire_cron(self, workflow_id: int) -> None:
        try:
            await self._engine.submit(
                workflow_id,
                "cron",
                {"fired_at": datetime.now(timezone.utc).isoformat()},
            )
        except EnginePaused:
            pass  # kill switch: triggers don't fire

    # ------------------------------------------------------------------ file drop

    def _is_ignored(self, rel: str) -> bool:
        return any(
            fnmatch(part, pattern)
            for part in Path(rel).parts
            for pattern in IGNORE_PATTERNS
        )

    async def handle_file_change(self, abs_path: str) -> None:
        root = Path(self._settings.atlas_root).resolve()
        try:
            rel = Path(abs_path).resolve().relative_to(root).as_posix()
        except ValueError:
            return
        if self._is_ignored(rel) or self.provenance.check(abs_path):
            return
        loop = asyncio.get_running_loop()
        for wf_id, watch_path, glob, stability_s in self._file_watches:
            if not (rel == watch_path or rel.startswith(watch_path + "/")):
                continue
            if not fnmatch(Path(rel).name, glob):
                continue
            key = (wf_id, rel)
            existing = self._debounce.pop(key, None)
            if existing is not None:
                existing.cancel()  # stability window resets on every change
            def _schedule(k: tuple[int, str] = key) -> None:
                asyncio.ensure_future(self._fire_file(*k))

            self._debounce[key] = loop.call_later(stability_s, _schedule)

    async def _fire_file(self, workflow_id: int, rel: str) -> None:
        self._debounce.pop((workflow_id, rel), None)
        try:
            await self._engine.submit(workflow_id, "file_drop", {"file_path": rel})
        except EnginePaused:
            pass

    async def start_watcher(self) -> None:
        """One watchfiles.awatch task over atlas_root, routed per workflow."""
        import watchfiles

        async def _watch() -> None:
            async for changes in watchfiles.awatch(str(self._settings.atlas_root)):
                for _change, path in changes:
                    await self.handle_file_change(path)

        self._watch_task = asyncio.create_task(_watch())

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self.scheduler.start()

    async def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        if self._watch_task is not None:
            self._watch_task.cancel()
            self._watch_task = None
        for handle in self._debounce.values():
            handle.cancel()
        self._debounce.clear()
