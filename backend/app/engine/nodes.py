"""Node executor registry (MASTER_PLAN §6, PHASE_5 Task 5.2).

Each executor is ``async (NodeCtx) -> dict`` and raises :class:`NodeError` on
step failure. The engine owns run/step bookkeeping; executors only do the work
and return the node's output context.
"""

from __future__ import annotations

import asyncio
import shlex
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.engine.context import ExpressionError, render, safe_expr
from app.files.safe_path import PathViolation, resolve_safe
from app.notify import email as email_notify
from app.notify import telegram as telegram_notify


class NodeError(Exception):
    """Step failure — the engine records str(exc) as the step error."""


EmitFn = Callable[..., Awaitable[Any]]


@dataclass
class NodeCtx:
    node_id: str
    node_type: str
    config: dict[str, Any]
    ctx: dict[str, Any]              # run context: {"trigger": ..., "<node_id>": output}
    hermes: Any                      # HermesClient or MockHermes
    jail_root: Path                  # file/shell jail (dry-run shadow dir when dry_run)
    shell_allowlist: list[str]
    run_id: int
    workflow_id: int
    dry_run: bool = False
    emit: EmitFn = field(default=None)  # type: ignore[assignment]
    step_id: int | None = None
    # engine hook: lets cancel() call stop_run on the active hermes run
    register_hermes_run: Callable[[str], None] | None = None


def _render(nctx: NodeCtx, template: str) -> str:
    rendered, _warnings = render(template, nctx.ctx)
    return rendered


async def _exec_hermes_task(nctx: NodeCtx) -> dict[str, Any]:
    prompt = _render(nctx, str(nctx.config["prompt"]))
    timeout_s = float(nctx.config.get("timeout_s", 900))
    retries = int(nctx.config.get("retries", 0))
    session_key = nctx.config.get("session_key")

    last_error: str = "hermes task failed"
    for _attempt in range(retries + 1):
        try:
            run_id = await nctx.hermes.create_run(prompt, session_key=session_key)
            if nctx.register_hermes_run is not None:
                nctx.register_hermes_run(run_id)
            output: dict[str, Any] | None = None
            async with asyncio.timeout(timeout_s):
                async for event in nctx.hermes.run_events(run_id):
                    kind = event.get("type") or event.get("event") or ""
                    if nctx.emit is not None:
                        await nctx.emit(
                            "hermes.run_event",
                            f"hermes {kind or 'event'} ({run_id})",
                            hermes_run_id=run_id,
                            event=event,
                        )
                    if kind == "approval.request":
                        await _create_hermes_approval(nctx, run_id, event)
                    if kind in ("run.completed", "run.failed", "run.cancelled"):
                        if kind != "run.completed":
                            raise NodeError(event.get("error") or f"hermes {kind}")
                        output = {
                            "output_text": event.get("output_text")
                            or event.get("output", ""),
                            "hermes_run_id": run_id,
                            "usage": event.get("usage", {}),
                        }
                        break
            if output is None:
                raise NodeError("hermes stream ended without terminal event")
            return output
        except TimeoutError:
            last_error = f"timeout after {timeout_s:g}s"
        except NodeError as exc:
            last_error = str(exc)
        except Exception as exc:  # connection/protocol errors are retryable
            last_error = str(exc) or type(exc).__name__
    raise NodeError(last_error)


async def _create_hermes_approval(
    nctx: NodeCtx, hermes_run_id: str, event: dict[str, Any]
) -> None:
    """Record a Hermes-side approval request (PHASE_7 Task 7.2).

    ``external_ref`` encodes ``"<hermes_run_id>|<hermes_approval_id>"`` so the
    approvals router can call ``HermesClient.approve_run`` on resolve (the §4
    schema has no separate column for the Hermes approval id).
    """
    from app.db import get_session

    message = (
        str(event.get("message") or event.get("preview") or "")
        or f"Hermes run {hermes_run_id} requests approval"
    )
    external_ref = f"{hermes_run_id}|{event.get('approval_id', '')}"
    async with get_session() as session:
        result = await session.execute(
            text(
                "INSERT INTO approvals(run_id, step_id, kind, external_ref, message, "
                "status, requested_at) "
                "VALUES (:run_id, :step_id, 'hermes_run', :ref, :message, 'pending', :now) "
                "RETURNING id"
            ),
            {
                "run_id": nctx.run_id,
                "step_id": nctx.step_id,
                "ref": external_ref,
                "message": message,
                "now": datetime.now(timezone.utc).isoformat(),
            },
        )
        approval_id = result.scalar_one()
        await session.commit()
    if nctx.emit is not None:
        await nctx.emit(
            "approval.requested",
            f"hermes approval requested: {message}",
            approval_id=approval_id,
            hermes_run_id=hermes_run_id,
        )


async def _exec_file_op(nctx: NodeCtx) -> dict[str, Any]:
    op = str(nctx.config["op"])
    rel_path = _render(nctx, str(nctx.config["path"]))
    try:
        path = resolve_safe(nctx.jail_root, rel_path)
        dest_rel = nctx.config.get("dest")
        dest = (
            resolve_safe(nctx.jail_root, _render(nctx, str(dest_rel)))
            if dest_rel is not None
            else None
        )
    except PathViolation as exc:
        raise NodeError(str(exc)) from exc

    if op == "write":
        content = _render(nctx, str(nctx.config.get("content", "")))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"path": rel_path, "abs_path": str(path)}
    if op == "mkdir":
        path.mkdir(parents=True, exist_ok=True)
        return {"path": rel_path}
    if op == "delete":
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        else:
            raise NodeError(f"path not found: {rel_path}")
        return {"path": rel_path}
    if op in ("move", "copy"):
        if dest is None:
            raise NodeError(f"{op} requires dest")
        if not path.exists():
            raise NodeError(f"path not found: {rel_path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if op == "copy":
            if path.is_dir():
                shutil.copytree(path, dest)
            else:
                shutil.copy2(path, dest)
        else:
            shutil.move(str(path), str(dest))
        return {"path": rel_path, "dest": str(nctx.config["dest"])}
    raise NodeError(f"unknown file op {op!r}")


async def _exec_condition(nctx: NodeCtx) -> dict[str, Any]:
    expression = str(nctx.config["expression"])
    try:
        result = bool(safe_expr(expression, nctx.ctx))
    except ExpressionError as exc:
        raise NodeError(str(exc)) from exc
    return {"result": result}


async def _exec_notify_telegram(nctx: NodeCtx) -> dict[str, Any]:
    await telegram_notify.send(_render(nctx, str(nctx.config["message"])))
    return {}


async def _exec_notify_email(nctx: NodeCtx) -> dict[str, Any]:
    await email_notify.send(
        _render(nctx, str(nctx.config["subject"])),
        _render(nctx, str(nctx.config["message"])),
    )
    return {}


async def _exec_shell_command(nctx: NodeCtx) -> dict[str, Any]:
    command = _render(nctx, str(nctx.config["command"]))
    if not any(command.startswith(prefix) for prefix in nctx.shell_allowlist):
        raise NodeError("command not in allowlist")
    timeout_s = float(nctx.config.get("timeout_s", 60))
    cwd_rel = nctx.config.get("cwd")
    try:
        cwd = (
            resolve_safe(nctx.jail_root, str(cwd_rel))
            if cwd_rel
            else nctx.jail_root
        )
    except PathViolation as exc:
        raise NodeError(str(exc)) from exc

    argv = shlex.split(command)  # never a shell string
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise NodeError(f"timeout after {timeout_s:g}s") from None
    return {
        "stdout": stdout.decode("utf-8", errors="replace"),
        "exit_code": proc.returncode,
    }


async def _exec_gate_approval(nctx: NodeCtx) -> dict[str, Any]:
    from app.db import get_session

    message = _render(nctx, str(nctx.config["message"]))
    async with get_session() as session:
        result = await session.execute(
            text(
                "INSERT INTO approvals(run_id, step_id, kind, message, status, requested_at) "
                "VALUES (:run_id, :step_id, 'gate', :message, 'pending', :now) RETURNING id"
            ),
            {
                "run_id": nctx.run_id,
                "step_id": nctx.step_id,
                "message": message,
                "now": datetime.now(timezone.utc).isoformat(),
            },
        )
        approval_id = result.scalar_one()
        await session.commit()
    if nctx.emit is not None:
        await nctx.emit(
            "approval.requested",
            f"approval requested: {message}",
            approval_id=approval_id,
        )
    # The engine parks the run when it sees this marker.
    return {"waiting_approval": True, "approval_id": approval_id, "message": message}


async def _exec_trigger(nctx: NodeCtx) -> dict[str, Any]:
    # Trigger nodes don't execute — their payload is already in ctx["trigger"].
    return dict(nctx.ctx.get("trigger", {}))


NODE_EXECUTORS: dict[str, Callable[[NodeCtx], Awaitable[dict[str, Any]]]] = {
    "trigger.cron": _exec_trigger,
    "trigger.file_drop": _exec_trigger,
    "trigger.webhook": _exec_trigger,
    "trigger.manual": _exec_trigger,
    "hermes.task": _exec_hermes_task,
    "file.op": _exec_file_op,
    "logic.condition": _exec_condition,
    "notify.telegram": _exec_notify_telegram,
    "notify.email": _exec_notify_email,
    "shell.command": _exec_shell_command,
    "gate.approval": _exec_gate_approval,
}
