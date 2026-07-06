"""Workflow graph models + validation (MASTER_PLAN §6).

``validate_graph`` returns human-readable error strings, each naming the
offending node/edge id, so the router can 422 with a useful message.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

TRIGGER_TYPES = {
    "trigger.cron",
    "trigger.file_drop",
    "trigger.webhook",
    "trigger.manual",
}

# type → (required config fields, optional config fields)
NODE_CONFIG_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "trigger.cron": ({"expr"}, set()),
    "trigger.file_drop": ({"watch_path"}, {"glob", "stability_s"}),
    "trigger.webhook": ({"secret"}, set()),
    "trigger.manual": (set(), set()),
    "hermes.task": ({"prompt"}, {"context_files", "session_key", "timeout_s", "retries"}),
    "file.op": ({"op", "path"}, {"dest", "content"}),
    "logic.condition": ({"expression"}, set()),
    "notify.telegram": ({"message"}, set()),
    "notify.email": ({"subject", "message"}, set()),
    "shell.command": ({"command"}, {"cwd", "timeout_s"}),
    "gate.approval": ({"message"}, {"timeout_h", "notify"}),
}

FILE_OPS = {"move", "copy", "write", "delete", "mkdir"}


class Position(BaseModel):
    x: float = 0
    y: float = 0


class Node(BaseModel):
    id: str
    type: str
    position: Position = Position()
    config: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    id: str
    source: str
    target: str
    condition: str | None = None


class Graph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]


def _rel_path_ok(rel: str) -> bool:
    """Structural jail check for graph-config paths (mirrors files.safe_path)."""
    if not isinstance(rel, str) or "\x00" in rel or "\\" in rel:
        return False
    if rel.startswith(("/", "~")):
        return False
    if len(rel) >= 2 and rel[1] == ":":
        return False
    parts = PurePosixPath(rel).parts
    return ".." not in parts and not any(p.startswith("~") for p in parts)


def _validate_node_config(node: Node, errors: list[str]) -> None:
    required, optional = NODE_CONFIG_FIELDS[node.type]
    missing = required - set(node.config)
    if missing:
        errors.append(
            f"node {node.id!r}: missing config field(s) {sorted(missing)} for {node.type}"
        )
        return
    unknown = set(node.config) - required - optional
    if unknown:
        errors.append(f"node {node.id!r}: unknown config field(s) {sorted(unknown)}")

    if node.type == "trigger.cron":
        try:
            CronTrigger.from_crontab(str(node.config["expr"]))
        except ValueError:
            errors.append(f"node {node.id!r}: invalid cron expression {node.config['expr']!r}")
    if node.type == "file.op":
        if node.config.get("op") not in FILE_OPS:
            errors.append(f"node {node.id!r}: invalid file op {node.config.get('op')!r}")
        for field in ("path", "dest"):
            value = node.config.get(field)
            if value is not None and not _rel_path_ok(str(value)):
                errors.append(f"node {node.id!r}: {field} {value!r} escapes the jail")
    if node.type == "trigger.file_drop" and not _rel_path_ok(str(node.config["watch_path"])):
        errors.append(f"node {node.id!r}: watch_path escapes the jail")
    if node.type == "shell.command":
        cwd = node.config.get("cwd")
        if cwd is not None and not _rel_path_ok(str(cwd)):
            errors.append(f"node {node.id!r}: cwd escapes the jail")


def validate_graph(graph: Graph) -> list[str]:
    """Return a list of human-readable errors; empty means the graph is valid."""
    errors: list[str] = []

    seen_ids: set[str] = set()
    for node in graph.nodes:
        if node.id in seen_ids:
            errors.append(f"node {node.id!r}: duplicate node id")
        seen_ids.add(node.id)
        if node.type not in NODE_CONFIG_FIELDS:
            errors.append(f"node {node.id!r}: unknown node type {node.type!r}")
            continue
        _validate_node_config(node, errors)

    triggers = [n for n in graph.nodes if n.type in TRIGGER_TYPES]
    if len(triggers) == 0:
        errors.append("graph must contain exactly one trigger node (found none)")
    elif len(triggers) > 1:
        ids = ", ".join(repr(n.id) for n in triggers)
        errors.append(f"graph must contain exactly one trigger node (found {ids})")

    node_ids = {n.id for n in graph.nodes}
    for edge in graph.edges:
        for end, ref in (("source", edge.source), ("target", edge.target)):
            if ref not in node_ids:
                errors.append(f"edge {edge.id!r}: {end} references missing node {ref!r}")

    return errors
