"""Workflow engine core (PHASE_5 Task 5.3 — implements the mandated skeleton).

Invariants (PHASE_5 header):
- queue-of-1 per workflow (``asyncio.Lock`` per workflow id), global semaphore 2
- kill switch: ``global_pause=1`` → submit raises :class:`EnginePaused`
- every state change updates the DB row first, then appends an event
- restart recovery: ``running`` → ``failed`` ("interrupted by restart"),
  ``waiting_approval`` stays parked (approval still pending)
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.config import Settings
from app.db import get_session
from app.engine.mock import MockHermes
from app.engine.nodes import NODE_EXECUTORS, NodeCtx, NodeError
from app.engine.schemas import TRIGGER_TYPES, Graph
from app.events import append_event

# Deliberately coarse cost approximation until Hermes reports real cost:
# $1 per million tokens (input + output). Recorded in PROGRESS.md.
COST_USD_PER_TOKEN = 1.0 / 1_000_000


class EnginePaused(Exception):
    """Raised by submit() when the kill switch (global_pause=1) is engaged."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Engine:
    def __init__(
        self, hermes_factory: Callable[[], Any], settings: Settings
    ) -> None:
        self._hermes_factory = hermes_factory
        self._settings = settings
        self._global_sem = asyncio.Semaphore(2)
        self._wf_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._active_hermes: dict[int, tuple[Any, str]] = {}
        self._expiry_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ helpers

    def hermes(self) -> Any:
        """A fresh adapter from the configured factory (used by routers)."""
        return self._hermes_factory()

    def _wf_lock(self, workflow_id: int) -> asyncio.Lock:
        return self._wf_locks[workflow_id]

    async def _get_setting(self, key: str) -> str | None:
        async with get_session() as session:
            row = (
                await session.execute(
                    text("SELECT value FROM settings WHERE key=:k"), {"k": key}
                )
            ).one_or_none()
        return row.value if row else None

    async def _shell_allowlist(self) -> list[str]:
        raw = await self._get_setting("shell_allowlist")
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [str(p) for p in parsed] if isinstance(parsed, list) else []

    async def _update_run(self, run_id: int, **cols: Any) -> None:
        sets = ", ".join(f"{k}=:{k}" for k in cols)
        async with get_session() as session:
            await session.execute(
                text(f"UPDATE runs SET {sets} WHERE id=:run_id"),
                {**cols, "run_id": run_id},
            )
            await session.commit()

    async def _fetch_run(self, run_id: int) -> Any:
        async with get_session() as session:
            return (
                await session.execute(
                    text(
                        "SELECT id, workflow_id, status, trigger_kind, trigger_payload, "
                        "dry_run, cost_usd, tokens_in, tokens_out FROM runs WHERE id=:id"
                    ),
                    {"id": run_id},
                )
            ).one()

    async def _fetch_workflow(self, workflow_id: int) -> Any:
        async with get_session() as session:
            return (
                await session.execute(
                    text(
                        "SELECT id, name, graph, enabled, max_runs_per_hour, "
                        "budget_usd_per_run FROM workflows WHERE id=:id"
                    ),
                    {"id": workflow_id},
                )
            ).one()

    # ------------------------------------------------------------------ lifecycle

    async def startup(self) -> None:
        """Restart recovery: fail interrupted runs, keep parked ones parked."""
        async with get_session() as session:
            stuck = (
                await session.execute(
                    text("SELECT id, workflow_id FROM runs WHERE status IN ('running', 'queued')")
                )
            ).all()
            await session.execute(
                text(
                    "UPDATE runs SET status='failed', error='interrupted by restart', "
                    "finished_at=:now WHERE status IN ('running', 'queued')"
                ),
                {"now": _now_iso()},
            )
            await session.commit()
        self._expiry_task = asyncio.create_task(self._expiry_loop())
        for row in stuck:
            await append_event(
                "run.failed",
                "engine",
                "run interrupted by restart",
                workflow_id=row.workflow_id,
                run_id=row.id,
            )

    async def submit(
        self,
        workflow_id: int,
        trigger_kind: str,
        payload: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> int:
        if await self._get_setting("global_pause") == "1":
            raise EnginePaused("paused")

        wf = await self._fetch_workflow(workflow_id)

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        async with get_session() as session:
            count = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM runs "
                        "WHERE workflow_id=:wf AND created_at >= :cutoff"
                    ),
                    {"wf": workflow_id, "cutoff": cutoff},
                )
            ).scalar_one()

        now = _now_iso()
        payload_json = json.dumps(payload, separators=(",", ":"), default=str)

        if count >= wf.max_runs_per_hour:
            async with get_session() as session:
                result = await session.execute(
                    text(
                        "INSERT INTO runs(workflow_id, status, trigger_kind, trigger_payload, "
                        "dry_run, error, created_at, finished_at) "
                        "VALUES (:wf, 'failed', :tk, :tp, :dr, 'circuit breaker', :now, :now) "
                        "RETURNING id"
                    ),
                    {"wf": workflow_id, "tk": trigger_kind, "tp": payload_json,
                     "dr": int(dry_run), "now": now},
                )
                run_id = result.scalar_one()
                await session.commit()
            await append_event(
                "run.failed",
                "engine",
                f"circuit breaker: {wf.name} exceeded {wf.max_runs_per_hour} runs/hour",
                workflow_id=workflow_id,
                run_id=run_id,
            )
            return int(run_id)

        async with get_session() as session:
            result = await session.execute(
                text(
                    "INSERT INTO runs(workflow_id, status, trigger_kind, trigger_payload, "
                    "dry_run, created_at) VALUES (:wf, 'queued', :tk, :tp, :dr, :now) "
                    "RETURNING id"
                ),
                {"wf": workflow_id, "tk": trigger_kind, "tp": payload_json,
                 "dr": int(dry_run), "now": now},
            )
            run_id = int(result.scalar_one())
            await session.commit()
        await append_event(
            "run.started",
            "engine",
            f"run started: {wf.name} ({trigger_kind}{', dry-run' if dry_run else ''})",
            workflow_id=workflow_id,
            run_id=run_id,
        )
        task = asyncio.create_task(self._execute(run_id))
        self._tasks[run_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(run_id, None))
        return run_id

    # ------------------------------------------------------------------ execution

    async def _execute(self, run_id: int) -> None:
        run = await self._fetch_run(run_id)
        workflow_id = int(run.workflow_id)
        async with self._global_sem, self._wf_lock(workflow_id):
            wf = await self._fetch_workflow(workflow_id)
            graph = Graph.model_validate(json.loads(wf.graph))
            payload = json.loads(run.trigger_payload or "{}")
            ctx: dict[str, Any] = {"trigger": payload}

            await self._update_run(run_id, status="running", started_at=_now_iso())

            trigger = next(n for n in graph.nodes if n.type in TRIGGER_TYPES)
            start = [e.target for e in graph.edges if e.source == trigger.id]
            try:
                await self._run_graph(
                    run_id, wf, graph, ctx, start, executed=set(), dry_run=bool(run.dry_run)
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # defensive: engine bugs must not hang runs
                await self._fail_run(run_id, workflow_id, str(exc) or type(exc).__name__)

    async def _run_graph(
        self,
        run_id: int,
        wf: Any,
        graph: Graph,
        ctx: dict[str, Any],
        start: list[str],
        *,
        executed: set[str],
        dry_run: bool,
    ) -> None:
        nodes = {n.id: n for n in graph.nodes}
        workflow_id = int(wf.id)
        jail_root = (
            Path(self._settings.data_dir) / "dryrun"
            if dry_run
            else Path(self._settings.atlas_root)
        )
        jail_root.mkdir(parents=True, exist_ok=True)
        hermes = MockHermes() if dry_run else self._hermes_factory()
        allowlist = await self._shell_allowlist()

        async def emit(kind: str, summary: str, **payload: Any) -> None:
            await append_event(
                kind, "engine", summary, workflow_id=workflow_id, run_id=run_id, **payload
            )

        queue: deque[str] = deque(start)
        while queue:
            node_id = queue.popleft()
            if node_id in executed or node_id not in nodes:
                continue
            node = nodes[node_id]
            executed.add(node_id)

            async with get_session() as session:
                result = await session.execute(
                    text(
                        "INSERT INTO run_steps(run_id, node_id, node_type, status, input, "
                        "started_at) VALUES (:run, :nid, :ntype, 'running', :input, :now) "
                        "RETURNING id"
                    ),
                    {
                        "run": run_id,
                        "nid": node.id,
                        "ntype": node.type,
                        "input": json.dumps(node.config, separators=(",", ":"), default=str),
                        "now": _now_iso(),
                    },
                )
                step_id = int(result.scalar_one())
                await session.commit()
            await emit(
                "run.step_started",
                f"step {node.id} ({node.type}) started",
                node_id=node.id,
                node_type=node.type,
            )

            nctx = NodeCtx(
                node_id=node.id,
                node_type=node.type,
                config=node.config,
                ctx=ctx,
                hermes=hermes,
                jail_root=jail_root,
                shell_allowlist=allowlist,
                run_id=run_id,
                workflow_id=workflow_id,
                dry_run=dry_run,
                emit=emit,
                step_id=step_id,
                register_hermes_run=lambda hid: self._active_hermes.__setitem__(
                    run_id, (hermes, hid)
                ),
            )
            try:
                output = await NODE_EXECUTORS[node.type](nctx)
            except NodeError as exc:
                await self._finish_step(step_id, "failed", error=str(exc))
                await emit(
                    "run.step_finished",
                    f"step {node.id} failed: {exc}",
                    node_id=node.id,
                    status="failed",
                )
                await self._fail_run(run_id, workflow_id, f"step {node.id}: {exc}")
                return
            finally:
                self._active_hermes.pop(run_id, None)

            if node.type == "gate.approval" and output.get("waiting_approval"):
                async with get_session() as session:
                    await session.execute(
                        text("UPDATE run_steps SET status='waiting_approval' WHERE id=:id"),
                        {"id": step_id},
                    )
                    await session.commit()
                await self._update_run(run_id, status="waiting_approval")
                await emit(
                    "run.waiting_approval",
                    f"run waiting for approval: {output.get('message', '')}",
                    approval_id=output.get("approval_id"),
                    node_id=node.id,
                )
                await self._notify_gate(
                    node.config, str(output.get("message", "")), run_id
                )
                return  # park; resume() re-enters

            ctx[node.id] = output
            await self._finish_step(step_id, "succeeded", output=output)
            await emit(
                "run.step_finished",
                f"step {node.id} succeeded",
                node_id=node.id,
                status="succeeded",
            )

            usage = output.get("usage") if isinstance(output, dict) else None
            if isinstance(usage, dict):
                tokens_in = int(usage.get("input_tokens", 0))
                tokens_out = int(usage.get("output_tokens", 0))
                cost = (tokens_in + tokens_out) * COST_USD_PER_TOKEN
                run = await self._fetch_run(run_id)
                new_cost = run.cost_usd + cost
                await self._update_run(
                    run_id,
                    cost_usd=new_cost,
                    tokens_in=run.tokens_in + tokens_in,
                    tokens_out=run.tokens_out + tokens_out,
                )
                if wf.budget_usd_per_run is not None and new_cost > wf.budget_usd_per_run:
                    await self._update_run(
                        run_id,
                        status="budget_exceeded",
                        error=f"budget exceeded (${new_cost:.6f} > ${wf.budget_usd_per_run})",
                        finished_at=_now_iso(),
                    )
                    await emit(
                        "run.failed",
                        f"budget exceeded: ${new_cost:.6f} > ${wf.budget_usd_per_run}",
                    )
                    return

            if node.type == "logic.condition":
                label = "true" if output.get("result") else "false"
                out_edges = [
                    e for e in graph.edges if e.source == node.id and e.condition == label
                ]
            else:
                out_edges = [e for e in graph.edges if e.source == node.id]
            queue.extend(e.target for e in out_edges)

        # normal completion: mark unreached (non-trigger) nodes skipped
        await self._mark_unreached_skipped(run_id, graph, executed)
        await self._update_run(run_id, status="succeeded", finished_at=_now_iso())
        await emit("run.finished", f"run finished: {wf.name}")

    async def _notify_gate(
        self, config: dict[str, Any], message: str, run_id: int
    ) -> None:
        """Gate notify hook (PHASE_7 Task 7.2): message + run link per channel."""
        from app.notify import email as email_notify
        from app.notify import telegram as telegram_notify

        channels = config.get("notify") or []
        text_body = f"{message}\n{self._settings.public_url}/runs/{run_id}"
        if "telegram" in channels:
            await telegram_notify.send(text_body)
        if "email" in channels:
            await email_notify.send("ATLAS approval requested", text_body)

    async def expire_approvals(self) -> None:
        """Expire pending gate approvals past their node's timeout_h.

        Runs periodically from startup(); the run fails with
        ``"approval timed out"`` per PHASE_7 Task 7.2.
        """
        async with get_session() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT a.id, a.run_id, a.step_id, a.requested_at, "
                        "s.node_id, r.workflow_id "
                        "FROM approvals a "
                        "JOIN run_steps s ON s.id = a.step_id "
                        "JOIN runs r ON r.id = a.run_id "
                        "WHERE a.status='pending' AND a.kind='gate'"
                    )
                )
            ).all()
        if not rows:
            return
        now = datetime.now(timezone.utc)
        for row in rows:
            wf = await self._fetch_workflow(int(row.workflow_id))
            graph = Graph.model_validate(json.loads(wf.graph))
            node = next((n for n in graph.nodes if n.id == row.node_id), None)
            timeout_h = float(node.config.get("timeout_h", 24)) if node else 24.0
            requested = datetime.fromisoformat(row.requested_at)
            if requested.tzinfo is None:
                requested = requested.replace(tzinfo=timezone.utc)
            if now < requested + timedelta(hours=timeout_h):
                continue
            async with get_session() as session:
                await session.execute(
                    text(
                        "UPDATE approvals SET status='expired', resolved_at=:now, "
                        "resolved_via='timeout' WHERE id=:id AND status='pending'"
                    ),
                    {"now": _now_iso(), "id": row.id},
                )
                await session.execute(
                    text(
                        "UPDATE run_steps SET status='failed', "
                        "error='approval timed out', finished_at=:now WHERE id=:id"
                    ),
                    {"now": _now_iso(), "id": row.step_id},
                )
                await session.commit()
            await append_event(
                "approval.resolved", "engine", "approval expired (timed out)",
                workflow_id=int(row.workflow_id), run_id=int(row.run_id),
            )
            await self._fail_run(
                int(row.run_id), int(row.workflow_id), "approval timed out"
            )

    async def _expiry_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                await self.expire_approvals()
            except Exception:  # never let the loop die on a transient error
                pass

    async def shutdown(self) -> None:
        task = getattr(self, "_expiry_task", None)
        if task is not None:
            task.cancel()

    async def _mark_unreached_skipped(
        self, run_id: int, graph: Graph, executed: set[str]
    ) -> None:
        async with get_session() as session:
            have = {
                row.node_id
                for row in (
                    await session.execute(
                        text("SELECT node_id FROM run_steps WHERE run_id=:id"),
                        {"id": run_id},
                    )
                ).all()
            }
            now = _now_iso()
            for node in graph.nodes:
                if node.type in TRIGGER_TYPES or node.id in executed or node.id in have:
                    continue
                await session.execute(
                    text(
                        "INSERT INTO run_steps(run_id, node_id, node_type, status, "
                        "started_at, finished_at) "
                        "VALUES (:run, :nid, :ntype, 'skipped', :now, :now)"
                    ),
                    {"run": run_id, "nid": node.id, "ntype": node.type, "now": now},
                )
            await session.commit()

    async def _finish_step(
        self,
        step_id: int,
        status: str,
        *,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        async with get_session() as session:
            await session.execute(
                text(
                    "UPDATE run_steps SET status=:status, output=:output, error=:error, "
                    "finished_at=:now WHERE id=:id"
                ),
                {
                    "status": status,
                    "output": json.dumps(output or {}, separators=(",", ":"), default=str),
                    "error": error,
                    "now": _now_iso(),
                    "id": step_id,
                },
            )
            await session.commit()

    async def _fail_run(self, run_id: int, workflow_id: int, error: str) -> None:
        await self._update_run(
            run_id, status="failed", error=error, finished_at=_now_iso()
        )
        await append_event(
            "run.failed", "engine", f"run failed: {error}",
            workflow_id=workflow_id, run_id=run_id,
        )

    # ------------------------------------------------------------------ resume / cancel

    async def resume(self, run_id: int, decision: str) -> None:
        run = await self._fetch_run(run_id)
        if run.status != "waiting_approval":
            raise ValueError(f"run {run_id} is not waiting for approval")
        workflow_id = int(run.workflow_id)
        wf = await self._fetch_workflow(workflow_id)
        graph = Graph.model_validate(json.loads(wf.graph))

        async with get_session() as session:
            await session.execute(
                text(
                    "UPDATE approvals SET status=:d, resolved_at=:now, resolved_via='api' "
                    "WHERE run_id=:run AND status='pending'"
                ),
                {"d": decision, "now": _now_iso(), "run": run_id},
            )
            steps = (
                await session.execute(
                    text(
                        "SELECT id, node_id, status, output FROM run_steps "
                        "WHERE run_id=:id ORDER BY id"
                    ),
                    {"id": run_id},
                )
            ).all()
            await session.commit()

        gate = next(s for s in steps if s.status == "waiting_approval")
        async with get_session() as session:
            await session.execute(
                text(
                    "UPDATE run_steps SET status='succeeded', output=:out, finished_at=:now "
                    "WHERE id=:id"
                ),
                {
                    "out": json.dumps({"decision": decision}),
                    "now": _now_iso(),
                    "id": gate.id,
                },
            )
            await session.commit()
        await append_event(
            "approval.resolved", "engine", f"approval {decision}",
            workflow_id=workflow_id, run_id=run_id,
        )

        # rebuild run context from recorded step outputs
        ctx: dict[str, Any] = {"trigger": json.loads(run.trigger_payload or "{}")}
        executed: set[str] = set()
        for step in steps:
            executed.add(step.node_id)
            if step.status == "succeeded":
                try:
                    ctx[step.node_id] = json.loads(step.output or "{}")
                except json.JSONDecodeError:
                    ctx[step.node_id] = {}
        ctx[gate.node_id] = {"decision": decision}

        start = [
            e.target
            for e in graph.edges
            if e.source == gate.node_id and e.condition == decision
        ]
        await self._update_run(run_id, status="running")

        async def _continue() -> None:
            async with self._global_sem, self._wf_lock(workflow_id):
                try:
                    await self._run_graph(
                        run_id, wf, graph, ctx, start,
                        executed=executed, dry_run=bool(run.dry_run),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await self._fail_run(run_id, workflow_id, str(exc) or type(exc).__name__)

        task = asyncio.create_task(_continue())
        self._tasks[run_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(run_id, None))

    async def cancel(self, run_id: int) -> None:
        active = self._active_hermes.pop(run_id, None)
        if active is not None:
            client, hermes_run_id = active
            try:
                await client.stop_run(hermes_run_id)
            except Exception:
                pass  # best effort — the local run is cancelled regardless
        task = self._tasks.pop(run_id, None)
        if task is not None:
            task.cancel()
        run = await self._fetch_run(run_id)
        await self._update_run(
            run_id, status="cancelled", finished_at=_now_iso()
        )
        await append_event(
            "run.finished", "engine", "run cancelled",
            workflow_id=int(run.workflow_id), run_id=run_id,
        )
