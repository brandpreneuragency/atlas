"""Brain review queue service (PHASE_7 Task 7.3).

Parses pending review notes under ``03_brain/01_review/pending/`` and, on a
decision, dispatches a Hermes run that executes the ATLAS brain workflow.
The note itself is never moved here — Hermes performs the moves per the rules.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import frontmatter

from app.events import append_event
from app.files.safe_path import resolve_safe

PENDING_DIR = "03_brain/01_review/pending"

PROMPT_TEMPLATE = """Execute the ATLAS brain review workflow for the review note at
03_brain/01_review/pending/{name}. Decision: {decision}.
Follow the rules in ATLAS_CONTEXT.md exactly: on approval create the memory
note and knowledge source note, move the review note to approved/, and move
the raw file from its inbox location to 02_processed/<original-category>/;
on rejection only move the review note to rejected/ and the raw file to
02_processed/. Report each file you created or moved as a list when done."""

_PREVIEW_CHARS = 500


def pending_dir(atlas_root: Path) -> Path:
    return resolve_safe(atlas_root, PENDING_DIR)


def list_pending(atlas_root: Path) -> list[dict[str, Any]]:
    directory = pending_dir(atlas_root)
    if not directory.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.md")):
        try:
            post = frontmatter.loads(path.read_text(encoding="utf-8"))
        except Exception:
            post = frontmatter.Post(path.read_text(encoding="utf-8", errors="replace"))
        meta = {str(k): v for k, v in post.metadata.items()}
        items.append(
            {
                "name": path.name,
                "frontmatter": meta,
                "body_preview": post.content[:_PREVIEW_CHARS],
                "source_path": meta.get("source_path"),
            }
        )
    return items


def note_path(atlas_root: Path, name: str) -> Path:
    """Jail-checked path of a pending note (raises PathViolation on escape)."""
    return resolve_safe(atlas_root, f"{PENDING_DIR}/{name}")


async def decide(name: str, decision: str, hermes: Any) -> str:
    """Dispatch the brain-workflow Hermes run; returns the Hermes run id."""
    prompt = PROMPT_TEMPLATE.format(name=name, decision=decision)
    run_id = await hermes.create_run(prompt)
    await append_event(
        "review.decided",
        "review",
        f"review {decision}: {name} (hermes run {run_id})",
        hermes_run_id=run_id,
        note=name,
        decision=decision,
    )
    asyncio.create_task(_relay_run_events(hermes, run_id, name))
    return str(run_id)


async def _relay_run_events(hermes: Any, run_id: str, name: str) -> None:
    try:
        async for event in hermes.run_events(run_id):
            kind = event.get("type") or event.get("event") or "event"
            await append_event(
                "hermes.run_event",
                "review",
                f"review run {kind} ({name})",
                hermes_run_id=run_id,
                event=event,
            )
            if kind == "approval.request":
                await _create_approval(run_id, name, event)
    except Exception as exc:
        await append_event(
            "hermes.error", "review", f"review run relay failed: {exc}"
        )


async def _create_approval(run_id: str, name: str, event: dict[str, Any]) -> None:
    """Surface a Hermes approval.request in the ATLAS inbox.

    Same encoding as engine hermes.task steps: ``external_ref`` is
    ``"<hermes_run_id>|<hermes_approval_id>"`` so the approvals router can call
    ``HermesClient.approve_run`` on resolve. run_id/step_id stay NULL — this is
    not an engine run.
    """
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.db import get_session

    message = (
        str(event.get("message") or event.get("preview") or "")
        or f"Review run for {name} requests approval"
    )
    async with get_session() as session:
        result = await session.execute(
            text(
                "INSERT INTO approvals(kind, external_ref, message, status, requested_at) "
                "VALUES ('hermes_run', :ref, :message, 'pending', :now) RETURNING id"
            ),
            {
                "ref": f"{run_id}|{event.get('approval_id', '')}",
                "message": f"{message} ({name})",
                "now": datetime.now(timezone.utc).isoformat(),
            },
        )
        approval_id = result.scalar_one()
        await session.commit()
    await append_event(
        "approval.requested",
        "review",
        f"review run approval requested: {message}",
        approval_id=approval_id,
        hermes_run_id=run_id,
    )
