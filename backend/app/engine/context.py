"""Run-context templating + safe expression interpreter (PHASE_5 Task 5.2).

Templating is pure regex substitution — placeholders resolve against the run
context dict and nothing is ever executed.  Expressions are interpreted by a
hand-written AST walker with a strict node-type whitelist; the string is never
handed to the Python runtime for execution.
"""

from __future__ import annotations

import ast
import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

# Simple dotted lookup path: name(.name)* — anything else stays a literal.
_DOTTED = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*)*$")


def render(template: str, ctx: dict[str, Any]) -> tuple[str, list[str]]:
    """Substitute ``{{node.field}}`` placeholders from ``ctx``.

    Unknown or malformed placeholders are left as literals and reported in the
    returned warnings list.
    """
    warnings: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        expr = match.group(1)
        if not _DOTTED.match(expr):
            warnings.append(f"unresolved placeholder {expr!r}")
            return match.group(0)
        value: Any = ctx
        for part in expr.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                warnings.append(f"unresolved placeholder {expr!r}")
                return match.group(0)
        return str(value)

    return _PLACEHOLDER.sub(_sub, template), warnings


class ExpressionError(Exception):
    """Raised when an expression is malformed or uses disallowed constructs."""


_ALLOWED_NODES = (
    ast.Expression,
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
    ast.Name,
    ast.Attribute,
    ast.Subscript,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.In,
    ast.NotIn,
    ast.Eq,
    ast.NotEq,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Load,
)


def safe_expr(expr: str, ctx: dict[str, Any]) -> Any:
    """Interpret a whitelisted comparison expression against ``ctx``.

    The walker computes results itself — the expression string is never handed
    to the Python runtime for execution, and lookups resolve only into ``ctx``.
    """
    try:
        tree = ast.parse(expr, mode="eval")  # parse only — never executed
    except SyntaxError as exc:
        raise ExpressionError(f"disallowed expression: {exc.msg}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(
                f"disallowed expression: {type(node).__name__} not permitted"
            )

    def _lookup(container: Any, key: str) -> Any:
        if isinstance(container, dict) and key in container:
            return container[key]
        raise ExpressionError(f"unknown name {key!r} in expression")

    def _interp(node: ast.expr) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return _lookup(ctx, node.id)
        if isinstance(node, ast.Attribute):
            return _lookup(_interp(node.value), node.attr)
        if isinstance(node, ast.Subscript):
            key = _interp(node.slice)
            container = _interp(node.value)
            if isinstance(container, dict) and key in container:
                return container[key]
            raise ExpressionError(f"unknown subscript {key!r} in expression")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not _interp(node.operand)
        if isinstance(node, ast.BoolOp):
            values = [_interp(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            return any(values)
        if isinstance(node, ast.Compare):
            left = _interp(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = _interp(comparator)
                ok: bool
                if isinstance(op, ast.In):
                    ok = left in right
                elif isinstance(op, ast.NotIn):
                    ok = left not in right
                elif isinstance(op, ast.Eq):
                    ok = left == right
                elif isinstance(op, ast.NotEq):
                    ok = left != right
                elif isinstance(op, ast.Gt):
                    ok = left > right
                elif isinstance(op, ast.GtE):
                    ok = left >= right
                elif isinstance(op, ast.Lt):
                    ok = left < right
                else:  # ast.LtE — the whitelist admits nothing else
                    ok = left <= right
                if not ok:
                    return False
                left = right
            return True
        raise ExpressionError(
            f"disallowed expression: {type(node).__name__} not permitted"
        )

    return _interp(tree.body)
