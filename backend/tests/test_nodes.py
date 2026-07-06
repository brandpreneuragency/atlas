"""Task 5.2 — node executors (engine/nodes.py)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.engine.mock import MockHermes
from app.engine.nodes import NODE_EXECUTORS, NodeCtx, NodeError


def make_ctx(tmp_path, node_type, config, *, ctx=None, hermes=None, allowlist=None,
             dry_run=False, events=None):
    collected = events if events is not None else []

    async def emit(kind, summary, **payload):
        collected.append({"kind": kind, "summary": summary, **payload})

    return NodeCtx(
        node_id="nX",
        node_type=node_type,
        config=config,
        ctx=ctx or {},
        hermes=hermes or MockHermes(),
        jail_root=tmp_path,
        shell_allowlist=allowlist or [],
        run_id=1,
        workflow_id=1,
        dry_run=dry_run,
        emit=emit,
    )


# --- hermes.task -------------------------------------------------------------


@pytest.mark.asyncio
async def test_hermes_task_returns_output_and_relays_events(tmp_path):
    events = []
    nctx = make_ctx(
        tmp_path, "hermes.task",
        {"prompt": "Reply PONG", "timeout_s": 5, "retries": 0},
        events=events,
    )
    out = await NODE_EXECUTORS["hermes.task"](nctx)
    assert out["output_text"].startswith("MOCK OUTPUT for: Reply PONG")
    assert out["hermes_run_id"] == "mock-run-1"
    assert out["usage"]["input_tokens"] == 100
    assert any(e["kind"] == "hermes.run_event" for e in events)


@pytest.mark.asyncio
async def test_hermes_task_prompt_is_templated(tmp_path):
    hermes = MockHermes()
    nctx = make_ctx(
        tmp_path, "hermes.task",
        {"prompt": "Summarize {{trigger.file_path}}", "timeout_s": 5, "retries": 0},
        ctx={"trigger": {"file_path": "01_inbox/a.md"}},
        hermes=hermes,
    )
    out = await NODE_EXECUTORS["hermes.task"](nctx)
    assert "01_inbox/a.md" in out["output_text"]


class SlowHermes(MockHermes):
    async def run_events(self, run_id):
        await asyncio.sleep(10)
        yield {}


@pytest.mark.asyncio
async def test_hermes_task_timeout(tmp_path):
    nctx = make_ctx(
        tmp_path, "hermes.task",
        {"prompt": "p", "timeout_s": 0.05, "retries": 0},
        hermes=SlowHermes(),
    )
    with pytest.raises(NodeError, match="timeout after 0.05s"):
        await NODE_EXECUTORS["hermes.task"](nctx)


class FlakyHermes(MockHermes):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    async def run_events(self, run_id):
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("boom")
        async for event in super().run_events(run_id):
            yield event


@pytest.mark.asyncio
async def test_hermes_task_retries_once(tmp_path):
    hermes = FlakyHermes()
    nctx = make_ctx(
        tmp_path, "hermes.task",
        {"prompt": "p", "timeout_s": 5, "retries": 1},
        hermes=hermes,
    )
    out = await NODE_EXECUTORS["hermes.task"](nctx)
    assert hermes.attempts == 2
    assert "output_text" in out


# --- file.op ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_op_write_returns_provenance(tmp_path):
    nctx = make_ctx(
        tmp_path, "file.op",
        {"op": "write", "path": "out/x.md", "content": "hi {{n1.v}}"},
        ctx={"n1": {"v": "there"}},
    )
    out = await NODE_EXECUTORS["file.op"](nctx)
    assert out["path"] == "out/x.md"
    assert (tmp_path / "out" / "x.md").read_text(encoding="utf-8") == "hi there"
    assert out["abs_path"].endswith("x.md")


@pytest.mark.asyncio
async def test_file_op_move_copy_delete_mkdir(tmp_path):
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")

    out = await NODE_EXECUTORS["file.op"](
        make_ctx(tmp_path, "file.op", {"op": "copy", "path": "a.txt", "dest": "b.txt"})
    )
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "A"

    await NODE_EXECUTORS["file.op"](
        make_ctx(tmp_path, "file.op", {"op": "move", "path": "b.txt", "dest": "c.txt"})
    )
    assert not (tmp_path / "b.txt").exists()
    assert (tmp_path / "c.txt").exists()

    await NODE_EXECUTORS["file.op"](
        make_ctx(tmp_path, "file.op", {"op": "mkdir", "path": "newdir"})
    )
    assert (tmp_path / "newdir").is_dir()

    await NODE_EXECUTORS["file.op"](
        make_ctx(tmp_path, "file.op", {"op": "delete", "path": "c.txt"})
    )
    assert not (tmp_path / "c.txt").exists()
    assert out["path"] == "a.txt"
    assert out["dest"] == "b.txt"


@pytest.mark.asyncio
async def test_file_op_escape_fails(tmp_path):
    nctx = make_ctx(tmp_path, "file.op", {"op": "write", "path": "../evil.md", "content": "x"})
    with pytest.raises(NodeError):
        await NODE_EXECUTORS["file.op"](nctx)


# --- logic.condition ----------------------------------------------------------


@pytest.mark.asyncio
async def test_condition_true_false(tmp_path):
    ctx = {"n2": {"output_text": "PONG"}}
    out = await NODE_EXECUTORS["logic.condition"](
        make_ctx(tmp_path, "logic.condition", {"expression": "'PONG' in n2.output_text"}, ctx=ctx)
    )
    assert out["result"] is True

    out = await NODE_EXECUTORS["logic.condition"](
        make_ctx(tmp_path, "logic.condition", {"expression": "'NOPE' in n2.output_text"}, ctx=ctx)
    )
    assert out["result"] is False


@pytest.mark.asyncio
async def test_condition_disallowed_expression_fails(tmp_path):
    nctx = make_ctx(tmp_path, "logic.condition", {"expression": "__import__('os')"})
    with pytest.raises(NodeError, match="disallowed expression"):
        await NODE_EXECUTORS["logic.condition"](nctx)


# --- notify -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_telegram_calls_send_with_rendered_message(tmp_path):
    with patch("app.notify.telegram.send", new_callable=AsyncMock) as send:
        nctx = make_ctx(
            tmp_path, "notify.telegram", {"message": "Done: {{n1.v}}"}, ctx={"n1": {"v": "OK"}}
        )
        out = await NODE_EXECUTORS["notify.telegram"](nctx)
    send.assert_awaited_once_with("Done: OK")
    assert out == {}


@pytest.mark.asyncio
async def test_notify_email_calls_send(tmp_path):
    with patch("app.notify.email.send", new_callable=AsyncMock) as send:
        nctx = make_ctx(
            tmp_path, "notify.email",
            {"subject": "S {{n1.v}}", "message": "M {{n1.v}}"}, ctx={"n1": {"v": "1"}}
        )
        await NODE_EXECUTORS["notify.email"](nctx)
    send.assert_awaited_once_with("S 1", "M 1")


# --- shell.command --------------------------------------------------------------


@pytest.mark.asyncio
async def test_shell_command_allowlisted_runs(tmp_path):
    nctx = make_ctx(
        tmp_path, "shell.command",
        {"command": "git status", "timeout_s": 30},
        allowlist=["git "],
    )
    out = await NODE_EXECUTORS["shell.command"](nctx)
    assert "exit_code" in out
    assert "stdout" in out


@pytest.mark.asyncio
async def test_shell_command_not_allowlisted_fails(tmp_path):
    nctx = make_ctx(
        tmp_path, "shell.command",
        {"command": "rm -rf /", "timeout_s": 30},
        allowlist=["git "],
    )
    with pytest.raises(NodeError, match="command not in allowlist"):
        await NODE_EXECUTORS["shell.command"](nctx)


@pytest.mark.asyncio
async def test_shell_command_timeout_kills(tmp_path):
    nctx = make_ctx(
        tmp_path, "shell.command",
        {"command": "python -c \"import time; time.sleep(30)\"", "timeout_s": 0.2},
        allowlist=["python "],
    )
    with pytest.raises(NodeError, match="timeout"):
        await NODE_EXECUTORS["shell.command"](nctx)
