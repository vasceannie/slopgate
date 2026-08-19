"""Hypothesis references for style-limit AST rule classes."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.rules.python_ast._rules.style_limits import (
    PythonDeepNestingRule,
    PythonLongLineRule,
    PythonLongMethodRule,
    PythonLongParameterRule,
)


@given(strategies.integers(min_value=0, max_value=2))
def test_style_limit_rule_helper_names(value: int) -> None:
    assert (
        PythonLongMethodRule.__name__,
        PythonLongParameterRule.__name__,
        PythonLongLineRule.__name__,
        PythonDeepNestingRule.__name__,
        value,
    )[-1] == value
