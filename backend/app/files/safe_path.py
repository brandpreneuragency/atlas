"""Path jail — the security boundary for ALL file-manager filesystem access.

Every files route must resolve user-supplied paths through :func:`resolve_safe`
before touching the filesystem. Nothing outside ``root`` is ever reachable.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import unquote


class PathViolation(Exception):
    """Raised when a user-supplied path attempts to escape the jail."""


def _reject(rel: str, reason: str) -> None:
    raise PathViolation(f"illegal path {rel!r}: {reason}")


def resolve_safe(root: Path, rel: str) -> Path:
    """Resolve ``rel`` inside ``root``, raising :class:`PathViolation` on escape.

    Rejects absolute paths, drive letters, backslashes, null bytes, ``~``,
    ``..`` segments (checked again after one URL-decode pass), and symlinked
    ancestors that point outside the jail.
    """
    if "\x00" in rel:
        _reject(rel, "null byte")

    # URL-decode once and validate the decoded form as well, so `%2e%2e`
    # cannot smuggle a `..` segment past the checks below.
    for cand in {rel, unquote(rel)}:
        if "\x00" in cand:
            _reject(rel, "null byte")
        if "\\" in cand:
            _reject(rel, "backslash separator")
        if cand.startswith(("/", "~")):
            _reject(rel, "absolute or home-relative path")
        if len(cand) >= 2 and cand[1] == ":":
            _reject(rel, "drive letter")
        parts = PurePosixPath(cand).parts
        if ".." in parts:
            _reject(rel, "parent traversal")
        if any(p.startswith("~") for p in parts):
            _reject(rel, "home expansion")

    decoded = unquote(rel)
    root_resolved = root.resolve()
    joined = root_resolved.joinpath(*PurePosixPath(decoded).parts)
    resolved = joined.resolve(strict=False)
    if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
        _reject(rel, "resolves outside jail")

    # Walk each existing ancestor: a symlink inside the jail may point outside.
    current = root_resolved
    for part in PurePosixPath(decoded).parts:
        current = current / part
        if current.is_symlink():
            target = current.resolve(strict=False)
            if target != root_resolved and not target.is_relative_to(root_resolved):
                _reject(rel, "symlink escapes jail")
        if not current.exists():
            break

    return joined
