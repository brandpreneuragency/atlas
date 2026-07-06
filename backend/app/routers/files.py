"""File manager API — every filesystem access goes through resolve_safe."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import anyio
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.events import append_event
from app.files.safe_path import PathViolation, resolve_safe

MAX_READ_BYTES = 2 * 1024 * 1024

router = APIRouter(prefix="/api/files")


def _safe(request: Request, rel: str) -> Path:
    try:
        return resolve_safe(request.app.state.settings.atlas_root, rel)
    except PathViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _must_exist(path: Path, rel: str) -> Path:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"not found: {rel}")
    return path


class WriteBody(BaseModel):
    path: str
    content: str
    expected_mtime: float | None = None


class MkdirBody(BaseModel):
    path: str


class TransferBody(BaseModel):
    paths: list[str]
    dest: str
    overwrite: bool = False


class DeleteBody(BaseModel):
    paths: list[str]
    recursive: bool = False


@router.get("/tree")
async def tree(request: Request, path: str = "") -> dict[str, Any]:
    target = _must_exist(_safe(request, path), path)
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="not a directory")

    def _list() -> list[dict[str, Any]]:
        entries = []
        for child in target.iterdir():
            stat = child.stat()
            entries.append(
                {
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
            )
        entries.sort(key=lambda e: (not e["is_dir"], str(e["name"]).lower()))
        return entries

    return {"entries": await anyio.to_thread.run_sync(_list)}


@router.get("/read")
async def read(request: Request, path: str) -> dict[str, Any]:
    target = _must_exist(_safe(request, path), path)
    if target.is_dir():
        raise HTTPException(status_code=400, detail="is a directory")
    stat = target.stat()
    if stat.st_size > MAX_READ_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 2MB read limit")
    content = await anyio.to_thread.run_sync(
        lambda: target.read_text(encoding="utf-8", errors="replace")
    )
    return {"content": content, "mtime": stat.st_mtime, "truncated": False}


@router.put("/write", status_code=204)
async def write(request: Request, body: WriteBody) -> None:
    target = _safe(request, body.path)
    if body.expected_mtime is not None:
        if not target.exists():
            raise HTTPException(status_code=409, detail="file no longer exists")
        if target.stat().st_mtime != body.expected_mtime:
            raise HTTPException(
                status_code=409, detail="file changed on disk (mtime mismatch)"
            )
    created = not target.exists()

    def _write() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.content, encoding="utf-8")

    await anyio.to_thread.run_sync(_write)
    kind = "file.created" if created else "file.changed"
    verb = "created" if created else "saved"
    await append_event(kind, "files", f"{verb} {body.path}", path=body.path)


@router.post("/mkdir", status_code=204)
async def mkdir(request: Request, body: MkdirBody) -> None:
    target = _safe(request, body.path)
    if target.exists():
        raise HTTPException(status_code=409, detail="already exists")
    await anyio.to_thread.run_sync(lambda: target.mkdir(parents=True))
    await append_event(
        "file.created", "files", f"created folder {body.path}", path=body.path
    )


def _validate_transfer(
    request: Request, body: TransferBody
) -> list[tuple[str, Path, str, Path]]:
    """Pre-validate ALL sources/targets so bulk ops act atomically."""
    dest_dir = _must_exist(_safe(request, body.dest), body.dest)
    if not dest_dir.is_dir():
        raise HTTPException(status_code=400, detail="dest is not a directory")
    plan = []
    for rel in body.paths:
        source = _safe(request, rel)
        if not source.exists():
            # batch validation failure → whole request rejected, nothing moved
            raise HTTPException(status_code=400, detail=f"source missing: {rel}")
        target_rel = f"{body.dest}/{source.name}" if body.dest else source.name
        target = _safe(request, target_rel)
        if target.exists() and not body.overwrite:
            raise HTTPException(
                status_code=409, detail=f"target exists: {target_rel}"
            )
        plan.append((rel, source, target_rel, target))
    return plan


@router.post("/move", status_code=204)
async def move(request: Request, body: TransferBody) -> None:
    plan = _validate_transfer(request, body)

    def _move() -> None:
        for _, source, _, target in plan:
            if target.exists():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(source), str(target))

    await anyio.to_thread.run_sync(_move)
    for rel, _, target_rel, _ in plan:
        await append_event(
            "file.changed",
            "files",
            f"moved {rel} → {target_rel}",
            path=target_rel,
        )


@router.post("/copy", status_code=204)
async def copy(request: Request, body: TransferBody) -> None:
    plan = _validate_transfer(request, body)

    def _copy() -> None:
        for _, source, _, target in plan:
            if source.is_dir():
                shutil.copytree(
                    str(source), str(target), dirs_exist_ok=body.overwrite
                )
            else:
                shutil.copy2(str(source), str(target))

    await anyio.to_thread.run_sync(_copy)
    for rel, _, target_rel, _ in plan:
        await append_event(
            "file.created",
            "files",
            f"copied {rel} → {target_rel}",
            path=target_rel,
        )


@router.post("/delete", status_code=204)
async def delete(request: Request, body: DeleteBody) -> None:
    plan = []
    for rel in body.paths:
        target = _must_exist(_safe(request, rel), rel)
        if target.is_dir() and any(target.iterdir()) and not body.recursive:
            raise HTTPException(
                status_code=400,
                detail=f"directory not empty (pass recursive:true): {rel}",
            )
        plan.append((rel, target))

    def _delete() -> None:
        for _, target in plan:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()

    await anyio.to_thread.run_sync(_delete)
    for rel, _ in plan:
        await append_event("file.deleted", "files", f"deleted {rel}", path=rel)


@router.post("/upload", status_code=201)
async def upload(
    request: Request,
    path: str = Form(""),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    dest_dir = _must_exist(_safe(request, path), path)
    if not dest_dir.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")
    name = file.filename or ""
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid filename")
    target_rel = f"{path}/{name}" if path else name
    target = _safe(request, target_rel)
    content = await file.read()
    await anyio.to_thread.run_sync(lambda: target.write_bytes(content))
    await append_event(
        "file.created", "files", f"uploaded {target_rel}", path=target_rel
    )
    return {"path": target_rel}
