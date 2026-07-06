"""Task 5.2 — templating + safe expression interpreter (engine/context.py)."""

import pytest

from app.engine.context import ExpressionError, render, safe_expr

CTX = {
    "trigger": {"file_path": "01_inbox/note.md"},
    "n2": {"output_text": "PONG and more", "usage": {"input_tokens": 100}},
}


def test_render_substitutes_nested_keys():
    text, warnings = render(
        "Summarize {{trigger.file_path}} by {{n2.output_text}}", CTX
    )
    assert text == "Summarize 01_inbox/note.md by PONG and more"
    assert warnings == []


def test_render_unknown_key_leaves_literal_and_warns():
    text, warnings = render("Hello {{nope.field}}!", CTX)
    assert text == "Hello {{nope.field}}!"
    assert len(warnings) == 1
    assert "nope.field" in warnings[0]


def test_render_is_pure_substitution_never_executes():
    payload = "{{__import__('os')}}"
    text, warnings = render(payload, CTX)
    assert text == payload  # stays a literal string
    assert len(warnings) == 1


def test_render_no_placeholders_passthrough():
    text, warnings = render("plain text", CTX)
    assert text == "plain text"
    assert warnings == []


# --- safe_expr -------------------------------------------------------------


def test_expr_membership_true():
    assert safe_expr("'PONG' in n2.output_text", CTX) is True


def test_expr_comparison_and_boolop():
    assert safe_expr("n2.usage.input_tokens >= 100 and 'zz' not in trigger.file_path", CTX) is True
    assert safe_expr("not ('PONG' in n2.output_text)", CTX) is False


def test_expr_subscript_lookup():
    assert safe_expr("n2['output_text'] == 'PONG and more'", CTX) is True


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os')",
        "(lambda: 1)()",
        "[x for x in [1]]",
        "open('/etc/passwd')",
        "n2.output_text.upper()",
        "1 + 1",  # arithmetic BinOp not in whitelist
    ],
)
def test_expr_disallowed_nodes_fail_safely(expr):
    with pytest.raises(ExpressionError, match="disallowed expression"):
        safe_expr(expr, CTX)


def test_expr_unknown_name_fails():
    with pytest.raises(ExpressionError):
        safe_expr("missing_node.field == 1", CTX)
