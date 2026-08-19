"""Contract for style-limit AST rule identifiers."""

from __future__ import annotations

from slopgate.rules.python_ast._rules.style_limits import (
    PythonDeepNestingRule,
    PythonLongLineRule,
    PythonLongMethodRule,
    PythonLongParameterRule,
)


def test_style_limit_rule_ids() -> None:
    assert (
        PythonLongMethodRule.rule_id,
        PythonLongParameterRule.rule_id,
        PythonLongLineRule.rule_id,
        PythonDeepNestingRule.rule_id,
    ) == ("PY-CODE-008", "PY-CODE-009", "PY-CODE-010", "PY-CODE-011")
