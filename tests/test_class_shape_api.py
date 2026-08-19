"""Contract for class-shape AST helpers and rules."""

from __future__ import annotations

import ast

from slopgate.rules.python_ast._rules.class_shape import (
    PythonGodClassRule,
    PythonThinWrapperRule,
    is_wrapper_candidate,
    thin_wrapper_extract_single_call,
)


def test_is_wrapper_candidate_accepts_single_statement() -> None:
    node = ast.parse("def send():\n    return helper()\n").body[0]
    matched = is_wrapper_candidate(node)
    assert (node.name, matched) == ("send", True)


def test_thin_wrapper_extract_single_call_reads_return() -> None:
    node = ast.parse("def send():\n    return helper()\n").body[0]
    call_node = thin_wrapper_extract_single_call(node.body[0])
    assert ast.dump(call_node) == ast.dump(ast.parse("helper()").body[0].value)


def test_god_and_thin_rule_ids() -> None:
    assert (PythonGodClassRule.rule_id, PythonThinWrapperRule.rule_id) == (
        "PY-CODE-014",
        "PY-CODE-013",
    )
